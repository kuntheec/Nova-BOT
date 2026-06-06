#!/usr/bin/env python3
"""
Landing Page — Local Receiver v4
Family Member Batch System + Document Type Management
Paths configurable via environment variables (BASE_DIR).
"""

import json, os, datetime, random, pickle, base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
from dotenv import load_dotenv
load_dotenv()

# Configurable paths
BASE_DIR = os.getenv("BASE_DIR", r"D:\ImmigrationCases")
LEADS_FILE = os.getenv("LEADS_FILE", os.path.join(BASE_DIR, "_leads.json"))
CODES_FILE = os.getenv("CODES_FILE", os.path.join(BASE_DIR, "_verify_codes.json"))
CUSTOMERS_DB = os.getenv("CUSTOMERS_DB", os.path.join(BASE_DIR, "_Customers.json"))
PORT = int(os.getenv("LANDING_PORT", "5003"))

# Admin bypass credentials
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "kuntheec")
ADMIN_PERSONAL_CODE = os.getenv("ADMIN_PERSONAL_CODE", "201072")
MASTER_VERIFICATION_CODE = os.getenv("MASTER_VERIFICATION_CODE", "999999")

os.makedirs(BASE_DIR, exist_ok=True)

# ========== Customer DB Helpers ==========
def load_customers():
    if os.path.exists(CUSTOMERS_DB):
        with open(CUSTOMERS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schema_version": "2.0", "last_updated": "", "customers": [], "customers_by_channel": {}}

def save_customers(db):
    # Rebuild channel map
    db["customers_by_channel"] = {}
    for c in db.get("customers", []):
        ch = c.get("channels", {})
        if ch.get("messenger"):
            db["customers_by_channel"][f"messenger:{ch['messenger']}"] = c["customerId"]
        if ch.get("whatsapp"):
            db["customers_by_channel"][f"whatsapp:{ch['whatsapp']}"] = c["customerId"]
        for lid in ch.get("line", []):
            if lid:
                db["customers_by_channel"][f"line:{lid}"] = c["customerId"]
        email = c.get("profile", {}).get("email", "")
        if email:
            db["customers_by_channel"][f"email:{email}"] = c["customerId"]
        if not c.get("displayId"):
            c["displayId"] = c["customerId"]
    db["last_updated"] = datetime.datetime.now().isoformat()
    # Atomic write
    tmp_path = CUSTOMERS_DB + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CUSTOMERS_DB)
    except Exception as e:
        print(f"[ERROR] Atomic write failed: {e}")
        with open(CUSTOMERS_DB, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)

def next_customer_id(db):
    existing = set()
    for c in db.get("customers", []):
        if c.get("customerId", "").startswith("C"):
            try:
                existing.add(int(c["customerId"][1:]))
            except:
                pass
    n = 1
    while n in existing:
        n += 1
    return f"C{n:03d}"

def next_individual_id(customer):
    existing = set()
    for ind in customer.get("individuals", []):
        iid = ind.get("individualId", "")
        if iid.startswith("I"):
            try:
                existing.add(int(iid[1:]))
            except:
                pass
    n = 1
    while n in existing:
        n += 1
    return f"I{n:03d}"

def get_customer_by_email(db, email):
    email_lower = email.lower().strip()
    for c in db.get("customers", []):
        if c.get("profile", {}).get("email", "").lower().strip() == email_lower:
            return c
    return None

def submit_family_batch(data):
    db = load_customers()
    email = data.get("email", "").lower().strip()
    cust = get_customer_by_email(db, email)
    is_new = False
    if not cust:
        is_new = True
        cust = {
            "customerId": next_customer_id(db),
            "displayId": "",
            "profile": {
                "name": data.get("customer_name", ""),
                "phone": data.get("customer_phone", ""),
                "email": email
            },
            "channels": {
                "messenger": "",
                "whatsapp": "",
                "line": []
            },
            "individuals": [],
            "createdAt": datetime.datetime.now().isoformat(),
            "updatedAt": datetime.datetime.now().isoformat()
        }
        db["customers"].append(cust)

    channels = data.get("channels", {})
    if channels.get("messenger"):
        cust["channels"]["messenger"] = channels["messenger"]
    if channels.get("whatsapp"):
        cust["channels"]["whatsapp"] = channels["whatsapp"]
    if channels.get("line"):
        for lid in channels["line"]:
            if lid not in cust["channels"]["line"]:
                cust["channels"]["line"].append(lid)

    if is_new or data.get("update_profile", False):
        cust["profile"]["name"] = data.get("customer_name", cust["profile"]["name"])
        cust["profile"]["phone"] = data.get("customer_phone", cust["profile"]["phone"])

    new_individuals = []
    for ind_data in data.get("individuals", []):
        existing = None
        for existing_ind in cust.get("individuals", []):
            if existing_ind.get("name") == ind_data.get("name") and existing_ind.get("relationship") == ind_data.get("relationship"):
                existing = existing_ind
                break
        if existing:
            existing["phone"] = ind_data.get("phone", existing.get("phone", ""))
            existing["topic"] = ind_data.get("topic", existing.get("topic", ""))
            existing["updated_at"] = datetime.datetime.now().isoformat()
            new_individuals.append(existing)
        else:
            iid = next_individual_id(cust)
            new_ind = {
                "individualId": iid,
                "name": ind_data.get("name", ""),
                "phone": ind_data.get("phone", ""),
                "relationship": ind_data.get("relationship", "other"),
                "topic": ind_data.get("topic", ""),
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat()
            }
            cust["individuals"].append(new_ind)
            new_individuals.append(new_ind)

    cust["updatedAt"] = datetime.datetime.now().isoformat()
    if not cust.get("displayId"):
        cust["displayId"] = cust["customerId"]

    save_customers(db)

    leads = []
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            try:
                leads = json.load(f)
                if not isinstance(leads, list):
                    leads = []
            except:
                leads = []

    for ind in new_individuals:
        lead_entry = {
            "name": ind["name"],
            "phone": ind["phone"],
            "email": email,
            "line_id": channels.get("line", [""])[0] if channels.get("line") else "",
            "messenger_id": channels.get("messenger", ""),
            "whatsapp": channels.get("whatsapp", ""),
            "topic": ind.get("topic", ""),
            "relationship": ind.get("relationship", "other"),
            "individual_id": ind["individualId"],
            "email_verified": True,
            "source": "landing_page_batch",
            "customer_type": "family_batch",
            "submitted_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat()
        }
        found = False
        for i, lead in enumerate(leads):
            if lead.get("email", "").lower() == email and lead.get("individual_id") == ind["individualId"]:
                leads[i] = lead_entry
                found = True
                break
        if not found:
            leads.append(lead_entry)

    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)

    return {
        "customer_id": cust["customerId"],
        "display_id": cust["displayId"],
        "individuals": [ind["individualId"] for ind in new_individuals],
        "is_new_customer": is_new
    }

def submit_lead(data):
    batch = {
        "email": data.get("email", ""),
        "customer_name": data.get("name", ""),
        "customer_phone": data.get("phone", ""),
        "channels": {
            "line": [data["line_id"]] if data.get("line_id") else [],
            "messenger": data.get("messenger_id", ""),
            "whatsapp": data.get("whatsapp", "")
        },
        "individuals": [{
            "name": data.get("name", ""),
            "phone": data.get("phone", ""),
            "relationship": data.get("relationship", "self"),
            "topic": data.get("topic", "")
        }]
    }
    return submit_family_batch(batch)

def get_customer_full_info(email):
    db = load_customers()
    customer = get_customer_by_email(db, email)
    if not customer:
        return None
    individuals = []
    for ind in customer.get("individuals", []):
        individuals.append({
            "individual_id": ind.get("individualId"),
            "name": ind.get("name"),
            "phone": ind.get("phone", ""),
            "relationship": ind.get("relationship", ""),
            "topic": ind.get("topic", ""),
            "created_at": ind.get("created_at", "")
        })
    return {
        "customer_id": customer["customerId"],
        "display_id": customer.get("displayId", customer["customerId"]),
        "name": customer["profile"]["name"],
        "phone": customer["profile"]["phone"],
        "email": customer["profile"]["email"],
        "line_id": customer["channels"].get("line", [""])[0] if customer["channels"].get("line") else "",
        "messenger_id": customer["channels"].get("messenger", ""),
        "whatsapp": customer["channels"].get("whatsapp", ""),
        "created_at": customer.get("createdAt", ""),
        "individuals": individuals
    }

# ========== Verification Codes ==========
def load_codes():
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_codes(codes):
    with open(CODES_FILE, "w") as f:
        json.dump(codes, f, indent=2)

def generate_code(email):
    codes = load_codes()
    code = str(random.randint(100000, 999999))
    codes[email] = {
        "code": code,
        "expires": (datetime.datetime.now() + datetime.timedelta(minutes=2)).isoformat()
    }
    save_codes(codes)
    return code

def verify_code(email, user_code):
    codes = load_codes()
    if email not in codes:
        return False, "ไม่พบรหัสยืนยันสำหรับอีเมลนี้"
    entry = codes[email]
    if entry["code"] != user_code:
        return False, "รหัสยืนยันไม่ถูกต้อง"
    expiry = datetime.datetime.fromisoformat(entry["expires"])
    if datetime.datetime.now() > expiry:
        del codes[email]
        save_codes(codes)
        return False, "รหัสยืนยันหมดอายุแล้ว กรุณาขอรหัสใหม่"
    del codes[email]
    save_codes(codes)
    return True, "ยืนยันอีเมลสำเร็จ"

def send_email(to_email, subject, body):
    import traceback
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = os.getenv("GMAIL_TOKEN_FILE", r"D:\OpenClawData\.openclaw\gmail\tokens\biz.pickle")
        if not os.path.exists(token_file):
            print(f"[EMAIL] Token not found: {token_file}")
            return False

        with open(token_file, "rb") as f:
            creds = pickle.load(f)
        if creds.expired:
            creds.refresh(Request())
            with open(token_file, "wb") as f:
                pickle.dump(creds, f)

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        message = MIMEText(body, "plain", "utf-8")
        message["to"] = to_email
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        traceback.print_exc()
        return False

class LandingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode("utf-8"))
        path = self.path.replace("/landing", "")

        if path == "/submit-family":
            try:
                result = submit_family_batch(data)
                self._json_response(200, {"status": "received", "data": result})
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json_response(500, {"error": str(e)})

        elif path == "/submit":
            try:
                result = submit_lead(data)
                self._json_response(200, {"status": "received", "data": result})
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json_response(500, {"error": str(e)})

        elif path == "/send-code":
            email = data.get("email", "")
            if not email:
                self._json_response(400, {"error": "กรุณากรอกอีเมล"})
                return
            code = generate_code(email)
            subject = "🔐 รหัสยืนยันอีเมล — The Global Manpower"
            body_text = f"""
สวัสดี,

รหัสยืนยันอีเมลของคุณคือ: {code}

รหัสนี้มีอายุ 2 นาที
หากคุณไม่ได้ขอรหัสยืนยัน กรุณาละเว้นอีเมลนี้

—
The Global Manpower Immigration Services
tgm.kuntheec@gmail.com
"""
            sent = send_email(email, subject, body_text)
            if sent:
                self._json_response(200, {"status": "sent", "message": "ส่งรหัสยืนยันไปยังอีเมลของคุณแล้ว"})
            else:
                self._json_response(500, {"error": "ไม่สามารถส่งอีเมลได้ กรุณาลองใหม่อีกครั้ง"})

        elif path == "/verify-code":
            email = data.get("email", "").strip().lower()
            code = data.get("code", "").strip()

            if code == MASTER_VERIFICATION_CODE:
                self._json_response(200, {"status": "verified", "message": "Master code accepted"})
                return

            if email == ADMIN_EMAIL and code == ADMIN_PERSONAL_CODE:
                self._json_response(200, {"status": "verified", "message": "Admin bypass"})
                return

            if not email or not code:
                self._json_response(400, {"error": "กรุณากรอกอีเมลและรหัสยืนยัน"})
                return
            ok, msg = verify_code(email, code)
            if ok:
                self._json_response(200, {"status": "verified", "message": msg})
            else:
                self._json_response(400, {"error": msg})

        elif path == "/get-customer":
            email = data.get("email", "")
            if not email:
                self._json_response(400, {"error": "กรุณากรอกอีเมล", "found": False})
                return
            info = get_customer_full_info(email)
            if info:
                self._json_response(200, {"found": True, "data": info, "db_version": "v2"})
            else:
                self._json_response(200, {"found": False, "data": {}, "db_version": "none"})

        elif path == "/get-family":
            email = data.get("email", "")
            if not email:
                self._json_response(400, {"error": "กรุณากรอกอีเมล", "individuals": []})
                return
            info = get_customer_full_info(email)
            if info:
                self._json_response(200, {
                    "individuals": info.get("individuals", []),
                    "customer_id": info["customer_id"]
                })
            else:
                self._json_response(200, {"individuals": [], "customer_id": ""})

        elif path == "/get-individual":
            email = data.get("email", "")
            individual_id = data.get("individual_id", "")
            if not email or not individual_id:
                self._json_response(400, {"error": "Missing email or individual_id"})
                return
            db = load_customers()
            customer = get_customer_by_email(db, email)
            if not customer:
                self._json_response(404, {"error": "Customer not found"})
                return
            ind = None
            for i in customer.get("individuals", []):
                if i.get("individualId") == individual_id:
                    ind = i
                    break
            if not ind:
                self._json_response(404, {"error": "Individual not found"})
                return
            self._json_response(200, {
                "individual": ind,
                "customer_id": customer["customerId"],
                "display_id": customer.get("displayId", customer["customerId"])
            })
        else:
            self._json_response(404, {"error": "Not found"})

    def do_GET(self):
        if self.path in ["/", "/health", "/ping"]:
            self._json_response(200, {"status": "ok", "service": "Landing Receiver v4"})
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        pass

def main():
    print("=" * 50)
    print("  Landing Page Receiver v4")
    print(f"  BASE_DIR: {BASE_DIR}")
    print("=" * 50)
    server = HTTPServer(("0.0.0.0", PORT), LandingHandler)
    print(f"[LANDING] Receiver on port {PORT}")
    print(f"[LANDING] Endpoints: /submit, /submit-family, /send-code, /verify-code, /get-customer, /get-family, /get-individual")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOPPED]")
        server.server_close()

if __name__ == "__main__":
    main()
