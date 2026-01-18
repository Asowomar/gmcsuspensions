import requests
from bs4 import BeautifulSoup
import json
import os
import hashlib
import time

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
        print(f"\n--- Monitoring: {url} ---")
        try:
            headers = {'User-Agent': 'GMC-Guardian-Monitor/2.0'}
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            text = res.text.lower()
            
            current_data = {
                "url": url,
                "hash": self.get_page_hash(res.text),
                "legal_pages": [p for p in ['refund', 'shipping', 'privacy', 'terms'] if p in text],
                "contact_info": {
                    "email": "@" in text,
                    "phone": any(char.isdigit() for char in text)
                },
                "price_elements": [tag.get_text().strip() for tag in soup.find_all(class_=lambda x: x and 'price' in x.lower())][:5]
            }

            if url in self.baseline:
                old_data = self.baseline[url]
                alerts = []
                
                # 1. Check for missing legal pages
                for p in old_data['legal_pages']:
                    if p not in current_data['legal_pages']:
                        alerts.append(f"CRITICAL RISK: Legal page '{p}' is missing or unreachable!")
                
                # 2. Check for price changes
                if old_data['price_elements'] != current_data['price_elements']:
                    alerts.append("WARNING: Prices on the page have changed. Update your GMC Feed immediately to avoid suspension!")

                # 3. Check for contact info removal
                if old_data['contact_info']['email'] and not current_data['contact_info']['email']:
                    alerts.append("RISK: Email address removed from site. This triggers 'Misrepresentation' flags.")

                if alerts:
                    print("🚨 ALERTS DETECTED:")
                    for a in alerts: print(f" - {a}")
                else:
                    print("✅ No critical changes detected. System Healthy.")
            else:
                print("ℹ️ Initial scan completed. Baseline saved for future monitoring.")
            
            self.baseline[url] = current_data
            self.save_baseline()
            
        except Exception as e:
            print(f"Error during scan: {e}")

if __name__ == "__main__":
    guardian = GMCGuardian()
    # Replace with the client's URL
    target_url = "https://www.example.com"
    
    # Run once for demonstration. In production, wrap this in a loop or cron job.
    guardian.audit_site(target_url)
