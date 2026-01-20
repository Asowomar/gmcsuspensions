import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class GMCScannerEngine:
    def __init__(self, base_url, max_products=5):
        self.base_url = self._normalize_url(base_url)
        self.domain = urlparse(self.base_url).netloc
        self.max_products = max_products
        self.session = self._setup_session()
        
        # Expanded Red Flags for GMC Misrepresentation
        self.red_flags = [
            r'guaranteed', r'miracle', r'100% safe', r'no risk', r'weight loss', 
            r'get rich', r'\bfree money\b', r'permanent results', r'instant cure',
            r'lowest price in the world', r'#1 in the world', r'official store' # if not official
        ]

    def _normalize_url(self, url):
        url = url.strip().lower()
        if not url.startswith(('http://', 'https://')): url = 'https://' + url
        return url.rstrip('/')

    def _setup_session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.headers.update({'User-Agent': 'GMC-Guardian-Enterprise/3.0 (Compliance-Bot)'})
        return s

    def analyze_content(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text().lower()
        found = [f for f in self.red_flags if re.search(f, text)]
        return ("Risk", f"Flags: {', '.join(found)}") if found else ("Compliant", "Safe")

    def audit_page(self, url, is_main=False):
        try:
            res = self.session.get(url, timeout=10)
            res.raise_for_status()
            text = res.text.lower()
            issues = []
            
            # Text Compliance
            verdict, reason = self.analyze_content(res.text)
            if verdict == "Risk": issues.append(reason)

            if is_main:
                policies = {
                    'Refund': ['refund', 'rückgabe', 'widerruf', 'retour'],
                    'Shipping': ['shipping', 'versand', 'levering'],
                    'Privacy': ['privacy', 'datenschutz', 'privacybeleid'],
                    'Terms': ['terms', 'agb', 'voorwaarden'],
                    'Legal': ['impressum', 'legal notice', 'colofon']
                }
                for p, keys in policies.items():
                    if not any(k in text for k in keys): issues.append(f"Missing {p} Policy")
                if '@' not in text: issues.append("No Contact Email")
            else:
                if not any(s in text for s in ['"@type":"product"', 'schema.org/product']): issues.append("Missing Schema")
                if not any(c in text for c in ['€', 'eur', '$', '£']): issues.append("Missing Currency")

            return {
                "url": url, "type": "Main" if is_main else "Product",
                "status": "Pass" if not issues else "Fail",
                "text_compliance": verdict, "details": "; ".join(issues) if issues else "Compliant"
            }
        except Exception as e:
            return {"url": url, "type": "Error", "status": "Error", "details": str(e)}

    def scan(self):
        try:
            main_res = self.session.get(self.base_url, timeout=10)
            main_data = self.audit_page(self.base_url, is_main=True)
            
            soup = BeautifulSoup(main_res.text, 'html.parser')
            links = list(set(urljoin(self.base_url, a['href']) for a in soup.find_all('a', href=True) 
                        if self.domain in urlparse(urljoin(self.base_url, a['href'])).netloc 
                        and ('/product' in a['href'])))[:self.max_products]

            with ThreadPoolExecutor(max_workers=5) as ex:
                results = [main_data] + list(ex.map(self.audit_page, links))
            
            score = max(0, 100 - (sum(1 for r in results if r['status'] == "Fail") * 15))
            return {"domain": self.domain, "score": score, "rows": results}
        except Exception as e:
            return {"error": str(e)}
