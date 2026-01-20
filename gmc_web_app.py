import os
import json
import re
import datetime
import logging
import requests
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- SENIOR CONFIGURATION ---
DEBUG = True
PORT = 5000
WEBHOOK_URL = ""  # n8n/Zapier endpoint
MAX_PRODUCT_PAGES = 5
TIMEOUT = 12

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

class GMCScannerEngine:
    """Senior-grade scanning engine with concurrency and robust error handling."""
    
    def __init__(self, base_url):
        self.base_url = self._normalize_url(base_url)
        self.domain = urlparse(self.base_url).netloc
        self.session = self._setup_session()
        self.red_flags = [
            r'guaranteed',
            r'miracle',
            r'100% safe',
            r'no risk',
            r'weight loss',
            r'get rich',
            r'\bfree money\b'
        ]

    def _normalize_url(self, url):
        url = url.strip().lower()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url.rstrip('/')

    def _setup_session(self):
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9,nl;q=0.8,de;q=0.7'
        })
        return session

    def analyze_text(self, html_content):
        text = BeautifulSoup(html_content, 'html.parser').get_text().lower()
        found = [flag for flag in self.red_flags if re.search(flag, text)]
        if found:
            return "Risk", f"Suspicious terms: {', '.join(found)}"
        return "Compliant", "No high-risk claims detected."

    def audit_page(self, url, is_main=False):
        try:
            response = self.session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            html = response.text
            text_lower = html.lower()
            
            issues = []
            verdict, reason = self.analyze_text(html)
            
            if is_main:
                # Policy keywords (Multi-language support)
                policies = {
                    'Refund': ['refund', 'rückgabe', 'widerruf', 'retour'],
                    'Shipping': ['shipping', 'versand', 'levering'],
                    'Privacy': ['privacy', 'datenschutz', 'privacybeleid'],
                    'Terms': ['terms', 'agb', 'voorwaarden'],
                    'Legal': ['impressum', 'legal notice', 'colofon']
                }
                for p, keys in policies.items():
                    if not any(k in text_lower for k in keys):
                        issues.append(f"Missing {p} Policy")
                
                if '@' not in text_lower: issues.append("No contact email found")
            else:
                # Technical Product Checks
                if not any(s in text_lower for s in ['"@type":"product"', '"@type": "product"', 'schema.org/product']):
                    issues.append("Missing JSON-LD Product Schema")
                if not any(c in text_lower for c in ['€', 'eur', '$', '£']):
                    issues.append("Currency symbol missing near price")

            if verdict == "Risk": issues.append(reason)

            return {
                "url": url,
                "type": "Main" if is_main else "Product",
                "status": "Pass" if not issues else "Fail",
                "text_compliance": verdict,
                "details": "; ".join(issues) if issues else "Compliant"
            }
        except Exception as e:
            logger.error(f"Error auditing {url}: {e}")
            return {"url": url, "type": "Error", "status": "Error", "text_compliance": "N/A", "details": f"Unreachable: {str(e)}"}

    def get_product_links(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            full_url = urljoin(self.base_url, a['href'])
            if self.domain in urlparse(full_url).netloc and ('/products/' in full_url or '/product/' in full_url):
                links.add(full_url)
            if len(links) >= MAX_PRODUCT_PAGES: break
        return list(links)

    def run_full_audit(self):
        logger.info(f"Starting full audit for {self.base_url}")
        try:
            main_res = self.session.get(self.base_url, timeout=TIMEOUT)
            main_data = self.audit_page(self.base_url, is_main=True)
            product_links = self.get_product_links(main_res.text)
            
            # Parallel execution for speed
            with ThreadPoolExecutor(max_workers=5) as executor:
                product_results = list(executor.map(self.audit_page, product_links))
            
            all_rows = [main_data] + product_results
            score = self._calculate_score(all_rows)
            
            self._log_to_webhook(all_rows)
            
            return {
                "domain": self.domain,
                "score": score,
                "rows": all_rows,
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": f"Critical failure: {str(e)}"}

    def _calculate_score(self, rows):
        if not rows: return 0
        fail_count = sum(1 for r in rows if r['status'] == "Fail")
        return max(0, 100 - (fail_count * 12))

    def _log_to_webhook(self, rows):
        if not WEBHOOK_URL: return
        for row in rows:
            payload = {"domain": self.domain, "timestamp": datetime.datetime.now().isoformat(), **row}
            try: requests.post(WEBHOOK_URL, json=payload, timeout=3)
            except: pass

# --- FLASK ROUTES ---

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GMC Guardian | Enterprise Audit</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @media print { .no-print { display: none; } }
    </style>
</head>
<body class="bg-slate-50 text-slate-900">
    <div class="max-w-5xl mx-auto py-12 px-4">
        <div class="bg-white rounded-2xl shadow-xl p-8">
            <div class="text-center mb-10">
                <h1 class="text-4xl font-extrabold text-indigo-600 mb-2">GMC Guardian</h1>
                <p class="text-slate-500">Enterprise-grade Google Merchant Center Compliance Auditor</p>
            </div>

            <div class="flex gap-4 mb-8 no-print">
                <input type="text" id="urlInput" placeholder="https://store-url.com" class="flex-1 p-4 border-2 border-slate-200 rounded-xl focus:border-indigo-500 outline-none transition">
                <button onclick="startAudit()" id="btn" class="bg-indigo-600 text-white px-8 py-4 rounded-xl font-bold hover:bg-indigo-700 transition">Run Deep Audit</button>
            </div>

            <div id="loader" class="hidden text-center py-10">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                <p class="text-slate-600">Analyzing domain and product deep-links...</p>
            </div>

            <div id="results" class="hidden">
                <div class="flex items-center justify-between mb-6">
                    <h2 class="text-2xl font-bold" id="domainTitle"></h2>
                    <div class="text-3xl font-black text-indigo-600" id="scoreVal"></div>
                </div>
                
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-100">
                                <th class="p-4 rounded-l-lg">Type</th>
                                <th class="p-4">URL</th>
                                <th class="p-4">Status</th>
                                <th class="p-4">Text Check</th>
                                <th class="p-4 rounded-r-lg">Details</th>
                            </tr>
                        </thead>
                        <tbody id="tableBody"></tbody>
                    </table>
                </div>
                
                <div class="mt-8 flex justify-center no-print">
                    <button onclick="window.print()" class="bg-emerald-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-emerald-700 transition">Download PDF Report</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function startAudit() {
            const url = document.getElementById('urlInput').value;
            if(!url) return;
            
            document.getElementById('loader').classList.remove('hidden');
            document.getElementById('results').classList.add('hidden');
            document.getElementById('btn').disabled = true;

            try {
                const res = await fetch('/audit?url=' + encodeURIComponent(url));
                const data = await res.json();
                
                document.getElementById('domainTitle').innerText = "Report for " + data.domain;
                document.getElementById('scoreVal').innerText = data.score + "%";
                
                const body = document.getElementById('tableBody');
                body.innerHTML = data.rows.map(r => `
                    <tr class="border-b border-slate-100 hover:bg-slate-50 transition">
                        <td class="p-4 font-semibold">${r.type}</td>
                        <td class="p-4 text-xs text-slate-500">${r.url}</td>
                        <td class="p-4"><span class="px-3 py-1 rounded-full text-xs font-bold ${r.status === 'Pass' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}">${r.status}</span></td>
                        <td class="p-4 text-sm">${r.text_compliance}</td>
                        <td class="p-4 text-xs text-slate-600">${r.details}</td>
                    </tr>
                `).join('');

                document.getElementById('results').classList.remove('hidden');
            } catch (e) {
                alert("Audit failed. Check console for details.");
            } finally {
                document.getElementById('loader').classList.add('hidden');
                document.getElementById('btn').disabled = false;
            }
        }
    </script>
</body>
</html>
''')

@app.route('/audit')
def audit():
    url = request.args.get('url')
    if not url: return jsonify({"error": "URL required"}), 400
    engine = GMCScannerEngine(url)
    return jsonify(engine.run_full_audit())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
