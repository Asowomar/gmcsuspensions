from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import datetime

app = Flask(__name__)
CORS(app)

# --- CONFIGURATIE ---
# Voor Google Sheets integratie via gspread (vereist service_account.json)
# Of gebruik een Webhook (n8n/Zapier) voor makkelijkere logging
WEBHOOK_URL = "" # Vul hier een n8n of Zapier webhook in voor automatische sheets logging

class GMCScanner:
    def __init__(self, base_url):
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        self.base_url = base_url.strip('/')
        self.domain = urlparse(self.base_url).netloc
        self.headers = {'User-Agent': 'Mozilla/5.0 (GMC-Audit-Bot/3.0)'}

    def get_links(self, html, limit=3):
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            url = urljoin(self.base_url, a['href'])
            if self.domain in urlparse(url).netloc and ('/products/' in url or '/product/' in url):
                links.add(url)
            if len(links) >= limit: break
        return list(links)

    def audit_page(self, url, is_main=False):
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            text = res.text.lower()
            issues = []
            
            checks = {
                "Policies": False,
                "Contact": False,
                "Schema": False,
                "Currency": False
            }

            if is_main:
                policies = ['refund', 'shipping', 'privacy', 'terms', 'impressum', 'widerruf', 'versand']
                if any(p in text for p in policies): checks["Policies"] = True
                else: issues.append("Missing Policies")
                
                if '@' in text: checks["Contact"] = True
                else: issues.append("Missing Contact Info")
            
            if not is_main or '/products/' in url:
                if any(s in text for s in ['"@type":"product"', '"@type": "product"']): checks["Schema"] = True
                else: issues.append("Missing JSON-LD Schema")
                
                if any(c in text for c in ['€', 'eur', '$']): checks["Currency"] = True
                else: issues.append("Missing Currency Symbol")

            return {"url": url, "issues": issues, "checks": checks, "status": "Pass" if not issues else "Fail"}
        except:
            return {"url": url, "issues": ["Error"], "checks": {}, "status": "Error"}

    def full_audit(self):
        main_audit = self.audit_page(self.base_url, is_main=True)
        product_links = self.get_links(requests.get(self.base_url, headers=self.headers).text)
        product_audits = [self.audit_page(l) for l in product_links]
        
        score = max(0, 100 - (len(main_audit['issues']) * 10 + sum(len(p['issues']) for p in product_audits) * 5))
        
        result = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "domain": self.domain,
            "score": score,
            "main_page": main_audit,
            "products": product_audits
        }
        
        # Log naar Webhook (voor Google Sheets)
        if WEBHOOK_URL:
            try: requests.post(WEBHOOK_URL, json=result, timeout=5)
            except: pass
            
        return result

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>GMC Guardian | Sheets Integrated</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 40px auto; background: #f4f7f6; }
        .card { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        input { width: 60%; padding: 12px; border: 1px solid #ddd; border-radius: 5px; }
        button { padding: 12px 20px; background: #0052cc; color: white; border: none; border-radius: 5px; cursor: pointer; }
        .result-row { border-bottom: 1px solid #eee; padding: 10px 0; }
        .status-pass { color: green; font-weight: bold; }
        .status-fail { color: red; font-weight: bold; }
    </style>
</head>
<body>
    <div class="card">
        <h1>GMC Audit & Sheets Logger</h1>
        <p>Voer een URL in om een compliance check uit te voeren en op te slaan.</p>
        <input type="text" id="url" placeholder="https://winkel.nl">
        <button onclick="run()">Start & Log</button>
        <div id="out"></div>
    </div>
    <script>
        async function run() {
            const url = document.getElementById('url').value;
            const out = document.getElementById('out');
            out.innerHTML = "Bezig met scannen en loggen naar spreadsheet...";
            const res = await fetch('/audit?url=' + encodeURIComponent(url));
            const data = await res.json();
            
            let html = `<h2>Score: ${data.score}%</h2><p>Data is verzonden naar de spreadsheet log.</p>`;
            html += `<h3>Hoofdpagina: <span class="status-${data.main_page.status.toLowerCase()}">${data.main_page.status}</span></h3>`;
            data.products.forEach(p => {
                html += `<div class="result-row"><strong>Product:</strong> ${p.url} - <span class="status-${p.status.toLowerCase()}">${p.status}</span></div>`;
            });
            out.innerHTML = html;
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
