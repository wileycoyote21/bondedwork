from http.server import BaseHTTPRequestHandler
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

CSLB_URL = "https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/LicenseDetail.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/CheckLicense.aspx",
}

def scrape_license(lic_num):
    try:
        resp = requests.get(
            CSLB_URL,
            params={"LicNum": lic_num},
            headers=HEADERS,
            timeout=15,
            allow_redirects=True
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to reach CSLB: {str(e)}"}

    soup = BeautifulSoup(resp.text, "html.parser")

    def get_text(element_id):
        el = soup.find(id=element_id)
        return el.get_text(strip=True) if el else None

    # Business name
    bus_info = soup.find(id="MainContent_BusInfo")
    business_name = None
    if bus_info:
        lines = [l.strip() for l in bus_info.get_text(separator="\n").splitlines() if l.strip()]
        business_name = lines[0] if lines else None

    # Expiration date
    expiration = get_text("MainContent_ExpDt")

    # License status
    status_td = soup.find(id="MainContent_Status")
    status = None
    status_type = "unknown"
    if status_td:
        strong = status_td.find("strong")
        if strong:
            status = strong.get_text(strip=True)
            text_lower = status.lower()
            if "current and active" in text_lower:
                status_type = "active"
            elif "suspended" in text_lower:
                status_type = "suspended"
            elif "expired" in text_lower:
                status_type = "expired"
            elif "cancelled" in text_lower or "canceled" in text_lower:
                status_type = "cancelled"
            else:
                status_type = "other"

    # Bond info
    bonding_row = soup.find(id="MainContent_BondingRow2")
    bond_status = None
    if bonding_row:
        bond_text = bonding_row.get_text(strip=True)
        bond_status = "On file" if bond_text else None

    # Workers comp
    wc_status = None
    wc_expiry = None
    page_text = soup.get_text(separator="\n")
    lines = page_text.splitlines()

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if "workers compensation" in line_stripped.lower() and "insurance with" in line_stripped.lower():
            wc_status = "Insured"
        if "exempt" in line_stripped.lower() and "workers" in line_stripped.lower():
            wc_status = "Exempt"
        if "no current" in line_stripped.lower() and "workers" in line_stripped.lower():
            wc_status = "No current WC"
        if re.match(r"Expire Date:\s*\d{2}/\d{2}/\d{4}", line_stripped):
            context = " ".join(lines[max(0, i-10):i+2]).lower()
            if "workers" in context or "compensation" in context or "policy" in context:
                wc_expiry = line_stripped.replace("Expire Date:", "").strip()

    # Days until expiration
    days_until_expiry = None
    if expiration:
        try:
            exp_date = datetime.strptime(expiration, "%m/%d/%Y")
            days_until_expiry = (exp_date - datetime.now()).days
        except ValueError:
            pass

    return {
        "license_number": lic_num,
        "business_name": business_name,
        "status": status,
        "status_type": status_type,
        "expiration_date": expiration,
        "days_until_expiry": days_until_expiry,
        "bond_status": bond_status,
        "wc_status": wc_status,
        "wc_expiry": wc_expiry,
        "source_url": f"{CSLB_URL}?LicNum={lic_num}",
    }


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        lic_num = None
        if "?" in self.path:
            query = self.path.split("?", 1)[1]
            for part in query.split("&"):
                if part.startswith("num="):
                    lic_num = part[4:].strip()
                    break

        if not lic_num:
            self._respond(400, {"error": "Missing license number. Use ?num=XXXXXX"})
            return

        if not re.match(r"^\d{1,10}$", lic_num):
            self._respond(400, {"error": "Invalid license number format."})
            return

        result = scrape_license(lic_num)
        status_code = 200 if "error" not in result else 502
        self._respond(status_code, result)

    def _respond(self, status_code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
