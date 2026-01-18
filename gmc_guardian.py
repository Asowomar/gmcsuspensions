import requests
from bs4 import BeautifulSoup
import json
import os
import hashlib

class GMCGuardian:
    def __init__(self, db_file="gmc_baseline.json"):
        self.db_file = db_file
        self.baseline = self.load_baseline()

    def load_baseline(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as f:
                return json.load(f)
        return {}

    def save_baseline(self):
        with open(self.db_file, 'w') as f:
            json.dump(self.baseline, f, indent=4)

    def get_page_hash(self, html_content):
        return hashlib.md5(html_content.encode('utf-16')).hexdigest()

    def audit_site(self, url):
        print(f"\n--- GMC Guardian Audit: {url} ---")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            text = res.text.lower()
            
            findings = []
            score = 100

            # 1. Legal Pages Check (Multi-language support)
            required_policies = {
                'impressum': ['impressum', 'legal notice'],
                'shipping': ['versand', 'shipping', 'delivery'],
                'return': ['rückgabe', 'widerruf', 'return', 'refund'],
                'privacy': ['datenschutz', 'privacy'],
                'terms': ['agb', 'terms', 'conditions']
            }
            
            found_policies = []
            for key, keywords in required_policies.items():
                if any(k in text for k in keywords):
                    found_policies.append(key)
                else:
                    findings.append(f"MISSING: {key.capitalize()} policy not detected.")
                    score -= 15

            # 2. Contact Info Check
            has_email = "@" in text
            has_phone = any(char.isdigit() for char in text) # Basic check
            if not has_email: 
                findings.append("MISSING: Contact email not found.")
                score -= 10
            if not has_phone:
                findings.append("MISSING: Phone number not found.")
                score -= 10

            # 3. Technical Check (Shopify/Schema)
            is_shopify = "cdn.shopify.com" in text
            has_schema = '"@type": "product"' in text or '"@type":"product"' in text
            
            if not has_schema:
                findings.append("WARNING: No Product Schema (JSON-LD) detected on this page.")
                score -= 10

            report = {
                "url": url,
                "score": max(0, score),
                "is_shopify": is_shopify,
                "found_policies": found_policies,
                "findings": findings,
                "status": "Healthy" if score > 85 else "At Risk"
            }

            print(json.dumps(report, indent=2))
            return report

        except Exception as e:
            print(f"Error during audit: {e}")
            return None

if __name__ == "__main__":
    guardian = GMCGuardian()
    guardian.audit_site("https://mialea.de")
