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
WEBHOOK_URL = "" # Vul hier je n8n/Zapier URL in

class GMCScanner:
    def __init__(self, base_url):
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        self.base_url = base_url.strip('/')
        self.domain = urlparse(self.base_url).netloc
        self.headers = {'User-Agent': 'Mozilla/5.0 (GMC-Audit-Bot/3.0)'}
        # Woorden die GMC vaak triggeren op 'Misrepresentation'
        self.red_flags = ['guaranteed', 'miracle', '100% safe', 'no risk', 'best price in the world', 'free money', 'weight loss']

    def analyze_text_compliance(self, text):
        found_flags = [flag for flag in self.red_flags if flag in text.lower()]
        if not found_flags:
            return "Compliant", "Geen verdachte teksten gevonden."
        return "Risk", f"Verdachte termen gevonden: {', '.join(found_flags)}"

    def get_links(self, html, limit=5):
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
            soup = BeautifulSoup(res.text, 'html.parser')
            text = res.text.lower()
            
            issues = []
            verdict, reason = self.analyze_text_compliance(res.text)
            
            if is_main:
                policies = ['refund', 'shipping', 'privacy', 'terms', 'impressum', 'widerruf', 'versand']
                if not any(p in text for p in policies): issues.append("Missing Policies")
                if '@' not in text: issues.append("Missing Contact Info")
            else:
                if not any(s in text for s in ['"@type":"product"', '"@type": "product"']): issues.append("Missing Schema")
                if not any(c in text for c in ['€', 'eur', '$']): issues.append("Missing Currency")

            if verdict == "Risk": issues.append(reason)

            return {
                "url": url,
                "type": "Main" if is_main else "Product",
                "status": "Pass" if not issues else "Fail",
                "text_compliance": verdict,
                "details": ", ".join(issues) if issues else "All checks passed"
            }
        except:
            return {"url": url, "type": "Error", "status": "Error", "text_compliance": "N/A", "details": "Page unreachable"}

    def full_audit(self):
        main_page_data = self.audit_page(self.base_url, is_main=True)
        
        try:
            res = requests.get(self.base_url, headers=self.headers, timeout=10)
            product_links = self.get_links(res.text)
        except: product_links = []

        all_rows = [main_page_data]
        for link in product_links:
            all_rows.append(self.audit_page(link))

        # Verstuur elke rij apart naar de webhook voor Google Sheets
        if WEBHOOK_URL:
            for row in all_rows:
                payload = {
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "domain": self.domain,
                    **row
                }
                try: requests.post(WEBHOOK_URL, json=payload, timeout=2)
                except: pass

        return {"domain": self.domain, "rows": all_rows, "score": self.calculate_score(all_rows)}

    def calculate_score(self, rows):
        fails = sum(1 for r in rows if r['status'] == "Fail")
        return max(0, 100 - (fails * 15))

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>GMC Guardian | Deep Sheets Logger</title>
    <style>
        body { font-family: sans-serif; max-width: 1000px; margin: 40px auto; background: #f0f4f8; }
        .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #0052cc; color: white; }
        .status-pass { color: #27ae60; font-weight: bold; }
        .status-fail { color: #c0392b; font-weight: bold; }
        .btn { padding: 12px 20px; background: #0052cc; color: white; border: none; border-radius: 5px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h1>GMC Deep Audit & Sheets Logger</h1>
        <p>Elke pagina wordt als een aparte rij gelogd in de spreadsheet.</p>
        <input type="text" id="url" style="width:60%; padding:10px;" placeholder="https://winkel.nl">
        <button class="btn" onclick="run()">Start Deep Scan</button>
        <div id="out"></div>
    </div>
    <script>
        async function run() {
            const out = document.getElementById('out');
            out.innerHTML = "<p>🔍 Bezig met diepe scan van alle pagina's en tekst-analyse...</p>";
            const res = await fetch('/audit?url=' + encodeURIComponent(document.getElementById('url').value));
            const data = await res.json();
            
            let html = `<h2>Eindscore: ${data.score}%</h2>`;
            html += `<table><tr><th>Type</th><th>URL</th><th>Status</th><th>Tekst Check</th><th>Details</th></tr>`;
            data.rows.forEach(r => {
                html += `<tr>
                    <td>${r.type}</td>
                    <td><small>${r.url}</small></td>
                    <td class="status-${r.status.toLowerCase()}">${r.status}</td>
                    <td>${r.text_compliance}</td>
                    <td><small>${r.details}</small></td>
                </tr>`;
            });
            html += `</table>`;
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
