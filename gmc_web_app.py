from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import threading

app = Flask(__name__)
CORS(app)

class GMCScanner:
    def __init__(self, base_url):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.headers = {'User-Agent': 'Mozilla/5.0 (GMC-Audit-Bot/3.0)'}

    def get_links(self, html, limit=5):
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            url = urljoin(self.base_url, a['href'])
            if self.domain in urlparse(url).netloc and '/products/' in url:
                links.add(url)
            if len(links) >= limit: break
        return list(links)

    def audit_page(self, url, is_main=False):
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            text = res.text.lower()
            
            issues = []
            if is_main:
                policies = ['refund', 'shipping', 'privacy', 'terms', 'impressum']
                for p in policies:
                    if p not in text:
                        issues.append(f"Missing {p.capitalize()} policy link.")
                
                if '@' not in text: issues.append("No contact email found.")
            
            # Product specific checks
            if '/products/' in url:
                if '"@type": "product"' not in text and '"@type":"product"' not in text:
                    issues.append("Missing Product Schema (JSON-LD).")
                if '€' not in text and 'eur' not in text: 
                    issues.append("Currency symbol (€) not detected near price.")

            return {"url": url, "issues": issues, "status": "Pass" if not issues else "Fail"}
        except:
            return {"url": url, "issues": ["Could not reach page"], "status": "Error"}

    def full_audit(self):
        try:
            res = requests.get(self.base_url, headers=self.headers, timeout=10)
            main_audit = self.audit_page(self.base_url, is_main=True)
            product_links = self.get_links(res.text)
            
            product_audits = []
            for link in product_links:
                product_audits.append(self.audit_page(link))
            
            return {
                "main_page": main_audit,
                "products": product_audits,
                "score": self.calculate_score(main_audit, product_audits)
            }
        except Exception as e:
            return {"error": str(e)}

    def calculate_score(self, main, products):
        total_issues = len(main['issues'])
        for p in products: total_issues += len(p['issues'])
        score = 100 - (total_issues * 5)
        return max(0, score)

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>GMC Guardian | Instant Audit</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 50px auto; text-align: center; background: #f4f7f6; }
        .card { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        input { width: 70%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
        button { padding: 10px 20px; background: #0052cc; color: white; border: none; border-radius: 5px; cursor: pointer; }
        #results { margin-top: 30px; text-align: left; }
        .issue { color: #c0392b; font-size: 0.9em; }
        .success { color: #27ae60; }
    </style>
</head>
<body>
    <div class="card">
        <h1>GMC Compliance Scanner</h1>
        <p>Enter your store URL to check for Google Merchant Center risks.</p>
        <input type="text" id="url" placeholder="https://yourstore.com">
        <button onclick="runAudit()">Start Audit</button>
        <div id="results"></div>
    </div>

    <script>
        async function runAudit() {
            const url = document.getElementById('url').value;
            const resDiv = document.getElementById('results');
            resDiv.innerHTML = "Scanning... please wait (checking main page and products)";
            
            try {
                const response = await fetch('/audit?url=' + encodeURIComponent(url));
                const data = await response.json();
                
                let html = `<h2>Score: ${data.score}/100</h2>`;
                html += `<h3>Main Page: ${data.main_page.status}</h3><ul>`;
                data.main_page.issues.forEach(i => html += `<li class="issue">${i}</li>`);
                html += "</ul><h3>Product Pages:</h3>";
                
                data.products.forEach(p => {
                    html += `<div><strong>${p.url}</strong>: ${p.status}</div><ul>`;
                    p.issues.forEach(i => html += `<li class="issue">${i}</li>`);
                    html += "</ul>";
                });
                
                resDiv.innerHTML = html;
            } catch (e) {
                resDiv.innerHTML = "Error running audit. Make sure the URL is correct.";
            }
        }
    </script>
</body>
</html>
''')

@app.route('/audit')
def audit():
    url = request.args.get('url')
    scanner = GMCScanner(url)
    return jsonify(scanner.full_audit())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
