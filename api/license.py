from http.server import BaseHTTPRequestHandler
import requests
from bs4 import BeautifulSoup
import json
import re

CSLB_URL = "https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/LicenseDetail.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/CheckLicense.aspx",
}

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        lic_num = "999944"
        if "?" in self.path:
            query = self.path.split("?", 1)[1]
            for part in query.split("&"):
                if part.startswith("num="):
                    lic_num = part[4:].strip()

        try:
            resp = requests.get(
                CSLB_URL,
                params={"LicNum": lic_num},
                headers=HEADERS,
                timeout=15,
                allow_redirects=True
            )
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text(separator=" | ")[:3000]

            found_ids = []
            for id_name in ["MainContent_BusInfo", "MainContent_ExpDt", "MainContent_Status", "MainContent_BondingRow2"]:
                el = soup.find(id=id_name)
                found_ids.append({id_name: el.get_text(strip=True) if el else "NOT FOUND"})

            result = {
                "status_code": resp.status_code,
                "final_url": resp.url,
                "found_ids": found_ids,
                "page_text_sample": page_text,
            }

        except Exception as e:
            result = {"error": str(e)}

        body = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
