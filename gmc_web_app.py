from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json

app = Flask(__name__)
CORS(app)

class GMCScanner:
    def __init__(self, base_url):
        # Bugfix: Ensure URL has a scheme
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        self.base_url = base_url.strip('/')
        self.domain = urlparse(self.base_url).netloc
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def get_links(self, html, limit=3):
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        # Bugfix: Better product link detection for Shopify and general stores
        for a in soup.find_all('a', href=True):
            url = urljoin(self.base_url, a['href'])
            parsed = urlparse(url)
            if self.domain in parsed.netloc and ('/products/' in url or '/product/' in url):
                links.add(url)
            if len(links) >= limit: break
        return list(links)

    def audit_page(self, url, is_main=False):
        try:
            res = requests.get(url, headers=self.headers, timeout=10, allow_redirects=True)
            soup = BeautifulSoup(res.text, 'html.parser')
            text = res.text.lower()
            
            issues = []
            # 1. Policy Checks (Main Page Only)
            if is_main:
                policies = {
                    'Refund': ['refund', 'rückgabe', 'widerruf'],
                    'Shipping': ['shipping', 'versand', 'lieferung'],
                    'Privacy': ['privacy', 'datenschutz'],
                    'Terms': ['terms', 'agb', 'conditions'],
                    'Impressum': ['impressum', 'legal notice']
                }
                for p, keywords in policies.items():
                    if not any(k in text for k in keywords):
                        issues.append(f"Missing {p} policy link or mention.")
                
                if '@' not in text: issues.append("No contact email found on homepage.")
            
            # 2. Technical Checks (Product Pages)
            if not is_main or '/products/' in url:
                has_schema = any(s in text for s in ['"@type":"product"', '"@type": "product"', 'schema.org/product'])
                if not has_schema:
                    issues.append("Missing Product Schema (JSON-LD) - Critical for GMC.")
                
                if '€' not in text and 'eur' not in text and '$' not in text:
                    issues.append("Currency symbol not detected near price.")

            return {"url": url, "issues": issues, "status": "Pass" if not issues else "Fail"}
        except Exception as e:
            return {"url": url, "issues": [f"Connection Error: {str(e)}"], "status": "Error"}

    def full_audit(self):
        try:
            res = requests.get(self.base_url, headers=self.headers, timeout=10)
            main_audit = self.audit_page(self.base_url, is_main=True)
            product_links = self.get_links(res.text)
            
            product_audits = []
            for link in product_links:
                product_audits.append(self.audit_page(link))
            
            total_issues = len(main_audit['issues']) + sum(len(p['issues']) for p in product_audits)
            score = max(0, 100 - (total_issues * 7))
            
            return {
                "main_page": main_audit,
                "products": product_audits,
                "score": score,
                "domain": self.domain
            }
        except Exception as e:
            return {"error": f"Failed to scan {self.base_url}: {str(e)}"}

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>GMC Guardian | Professional Audit Tool</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 900px; margin: 40px auto; background: #f0f2f5; color: #1c1e21; }
        .container { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
        .input-group { display: flex; gap: 10px; justify-content: center; margin-bottom: 20px; }
        input { flex: 1; padding: 12px; border: 2px solid #ddd; border-radius: 6px; font-size: 16px; }
        button { padding: 12px 24px; background: #0052cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
        button:hover { background: #0041a3; }
        .btn-pdf { background: #27ae60; margin-top: 20px; display: none; }
        #results { margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px; }
        .score-circle { width: 100px; height: 100px; border-radius: 50%; background: #f8f9fa; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold; margin: 0 auto 20px; border: 5px solid #0052cc; }
        .issue-list { list-style: none; padding: 0; }
        .issue-item { background: #fff5f5; border-left: 4px solid #c0392b; padding: 10px; margin-bottom: 8px; font-size: 14px; }
        .success-msg { color: #27ae60; font-weight: bold; }
        @media print { .no-print { display: none; } .container { box-shadow: none; border: none; } }
    </style>
</head>
<body>
    <div class="container" id="report-area">
        <div class="header">
            <h1>GMC Guardian Audit</h1>
            <p>Deep-scan compliance report for Google Merchant Center</p>
        </div>
        
        <div class="input-group no-print">
            <input type="text" id="url-input" placeholder="https://mialea.de">
            <button onclick="runAudit()">Analyze Store</button>
        </div>

        <div id="results"></div>
        <center><button class="btn-pdf no-print" id="pdf-btn" onclick="window.print()">Download Report as PDF</button></center>
    </div>

    <script>
        async function runAudit() {
            const url = document.getElementById('url-input').value;
            if(!url) return alert("Please enter a URL");
            
            const resDiv = document.getElementById('results');
            const pdfBtn = document.getElementById('pdf-btn');
            resDiv.innerHTML = "<center><p>🔍 Scanning main page and product deep-links... This may take 10-20 seconds.</p></center>";
            pdfBtn.style.display = "none";

            try {
                const response = await fetch('/audit?url=' + encodeURIComponent(url));
                const data = await response.json();
                
                if(data.error) {
                    resDiv.innerHTML = `<p style="color:red">${data.error}</p>`;
                    return;
                }

                let html = `<div class="score-circle">${data.score}%</div>`;
                html += `<h2 style="text-align:center">Audit for ${data.domain}</h2>`;
                
                // Main Page
                html += `<h3>Main Page Status: ${data.main_page.status}</h3>`;
                if(data.main_page.issues.length > 0) {
                    html += '<ul class="issue-list">' + data.main_page.issues.map(i => `<li class="issue-item">${i}</li>`).join('') + '</ul>';
                } else {
                    html += '<p class="success-msg">✅ Main page is fully compliant.</p>';
                }

                // Products
                html += `<h3>Product Page Deep-Scan (${data.products.length} pages)</h3>`;
                data.products.forEach(p => {
                    html += `<div style="margin-top:15px;"><strong>Page:</strong> <small>${p.url}</small></div>`;
                    if(p.issues.length > 0) {
                        html += '<ul class="issue-list">' + p.issues.map(i => `<li class="issue-item">${i}</li>`).join('') + '</ul>';
                    } else {
                        html += '<p class="success-msg">✅ Product page compliant.</p>';
                    }
                });

                resDiv.innerHTML = html;
                pdfBtn.style.display = "block";
            } catch (e) {
                resDiv.innerHTML = "<p style='color:red'>Error connecting to scanner. Please try again.</p>";
            }
        }
    </script>
</body>
</html>
''')

@app.route('/audit')
def audit():
    url = request.args.get('url')
    if not url: return jsonify({"error": "No URL provided"})
    scanner = GMCScanner(url)
    return jsonify(scanner.full_audit())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
