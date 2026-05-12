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
}

def scrape_license(lic_num):
    try:
        resp = requests.get(
            CSLB_URL,
            params={"LicNum": lic_num},
            headers=HEADERS,
            timeout=15
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to reach CSLB: {str(e)}"}

    soup = BeautifulSoup(resp.text, "html.parser")

    def get_text(element_id):
        el = soup.find(id=element_id)
        return el.get_text(strip=True) if el else None

    # Business name — first bold text in BusInfo cell
    bus_info = soup.find(id="MainContent_BusInfo")
    business_name = None
    if bus_info:
        lines = [l.strip() for l in bus_info.get_text(separator="\n").splitlines() if l.strip()]
        business_name = lines[0] if lines else None

    # Expiration date
    expiration = get_text("MainContent_ExpDt")

    # License status — inside MainContent_Status > span > strong
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

    # Bond info — BondingRow2
    bonding_row = soup.find(id="MainContent_BondingRow2")
    bond_status = None
    if bonding_row:
        bond_status = bonding_row.get_text(strip=True)

    # Workers comp — look for WC section text
    wc_status = None
    wc_expiry = None
    page_text = soup.get_text(separator="\n")
    lines = page_text.splitlines()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if "workers compensation" in line.lower() and "insurance with" in line.lower():
            wc_status = line
        if re.match(r"Expire Date:\s*\d{2}/\d{2}/\d{4}", line):
            # Make sure we're in the WC section by checking nearby lines
            context = " ".join(lines[max(0, i-10):i+2]).lower()
            if "workers" in context or "compensation" in context or "policy" in context:
                wc_expiry = line.replace("Expire Date:", "").strip()
        if "exempt from workers" in line.lower() or "workers' compensation exempt" in line.lower():
            wc_status = "Exempt"

    # Days until expiration
    days_until_expiry = None
    if expiration:
        try:
            from datetime import datetime
            exp_date = datetime.strptime(expiration, "%m/%d/%Y")
            delta = (exp_date - datetime.now()).days
            days_until_expiry = delta
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
        # Parse license number from query string
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
        pass  # suppress default logging
