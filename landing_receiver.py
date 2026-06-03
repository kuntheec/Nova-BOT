#!/usr/bin/env python3
"""
Landing Page — Local Receiver
รับข้อมูลจากลูกค้าที่กรอกฟอร์ม + Verify Email via Code
"""

import json, os, datetime, sys, random, string, pickle
from http.server import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
import base64

BASE_DIR = r"D:\ImmigrationCases"
LEADS_FILE = os.path.join(BASE_DIR, "_leads.json")
CODES_FILE = os.path.join(BASE_DIR, "_verify_codes.json")
PORT = 5003

os.makedirs(BASE_DIR, exist_ok=True)


# ── Verification Codes ─────────────────────────────────

def load_codes():
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_codes(codes):
    with open(CODES_FILE, "w") as f:
        json.dump(codes, f, indent=2)

def generate_code(email):
    """Generate 6-digit code and save with email + expiry"""
    codes = load_codes()
    code = str(random.randint(100000, 999999))
    codes[email] = {
        "code": code,
        "expires": (datetime.datetime.now() + datetime.timedelta(minutes=10)).isoformat()
    }
    save_codes(codes)
    return code

def get_customer_by_email(email):
    """Retrieve existing customer data by email"""
    leads = load_leads()
    for lead in leads:
        if lead.get("email", "").lower() == email.lower():
            return lead
    # Also check Customer DB
    try:
        cdb_path = r"D:\ImmigrationCases\_Customers.json"
        if os.path.exists(cdb_path):
            with open(cdb_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            for c in db.get("customers", []):
                if c.get("profile", {}).get("email", "").lower() == email.lower():
                    return {
                        "name": c["profile"]["name"],
                        "phone": c["profile"]["phone"],
                        "email": c["profile"]["email"],
                        "line_id": "",
                        "messenger_id": c["channels"].get("messenger", ""),
                        "whatsapp": c["channels"].get("whatsapp", ""),
                        "topic": ""
                    }
    except:
        pass
    return None


def verify_code(email, user_code):
    """Check if code is valid and not expired"""
    codes = load_codes()
    if email not in codes:
        return False, "ไม่พบรหัสยืนยันสำหรับอีเมลนี้"
    entry = codes[email]
    if entry["code"] != user_code:
        return False, "รหัสยืนยันไม่ถูกต้อง"
    expiry = datetime.datetime.fromisoformat(entry["expires"])
    if datetime.datetime.now() > expiry:
        # Remove expired code
        del codes[email]
        save_codes(codes)
        return False, "รหัสยืนยันหมดอายุแล้ว กรุณาขอรหัสใหม่"
    # Remove used code
    del codes[email]
    save_codes(codes)
    return True, "ยืนยันอีเมลสำเร็จ"


# ── Send Email via Gmail API ──────────────────────────

def send_email(to_email, subject, body):
    """Send email using biz Gmail account (tgm.kuntheec)"""
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = r"D:\OpenClawData\.openclaw\gmail\tokens\biz.pickle"
        if not os.path.exists(token_file):
            print(f"[EMAIL] Token not found: {token_file}")
            return False

        with open(token_file, "rb") as f:
            creds = pickle.load(f)
        if creds.expired:
            creds.refresh(Request())

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        message = MIMEText(body, "plain", "utf-8")
        message["to"] = to_email
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[EMAIL] Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")
        return False


# ── Customer Data ─────────────────────────────────────

def load_leads():
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_leads(leads):
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)

def add_or_update_customer(data):
    leads = load_leads()
    entry = {
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "line_id": data.get("line_id", ""),
        "messenger_id": data.get("messenger_id", ""),
        "whatsapp": data.get("whatsapp", ""),
        "topic": data.get("topic", ""),
        "email_verified": True,
        "source": "landing_page",
        "submitted_at": datetime.datetime.now().isoformat()
    }

    existing = None
    for lead in leads:
        if lead.get("email") == entry["email"]:
            existing = lead
            break

    if existing:
        existing.update(entry)
        existing["updated_at"] = datetime.datetime.now().isoformat()
        print(f"[LEAD] Updated: {entry['name']} ({entry['email']})")
    else:
        leads.append(entry)
        print(f"[LEAD] New: {entry['name']} ({entry['email']})")

    save_leads(leads)

    line_ids = [entry["line_id"]] if entry.get("line_id") else []
    sys.path.insert(0, r"D:\OpenClawData\workspace")
    try:
        import consolidate_messages
        consolidate_messages.add_customer(
            name=entry["name"],
            phone=entry["phone"],
            email=entry["email"],
            messenger_id=entry.get("messenger_id", ""),
            whatsapp_num=entry.get("whatsapp", ""),
            line_ids=line_ids
        )
        print(f"[CUSTOMER] Synced to Customer DB")
    except Exception as e:
        print(f"[CUSTOMER] Sync error: {e}")

    # Save individual lead file
    lead_dir = os.path.join(BASE_DIR, "_leads")
    os.makedirs(lead_dir, exist_ok=True)
    safe_name = entry["name"].replace(" ", "_")[:30]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    indv_path = os.path.join(lead_dir, f"{ts}_{safe_name}.json")
    with open(indv_path, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)

    return entry


# ── HTTP Handler ──────────────────────────────────────

class LandingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode("utf-8"))

        # Tailscale strips /landing prefix
        path = self.path.replace("/landing", "")

        if path in ("/save", "/landing/save"):
            print(f"\n[LANDING] Registration from {data.get('name')} ({data.get('email')})")
            entry = add_or_update_customer(data)
            self._json_response(200, {"status": "received"})

        elif path in ("/send-code", "/landing/send-code"):
            email = data.get("email", "")
            if not email:
                self._json_response(400, {"error": "กรุณากรอกอีเมล"})
                return

            code = generate_code(email)
            subject = "🔐 รหัสยืนยันอีเมล — The Global Manpower"
            body_text = f"""
สวัสดี,

รหัสยืนยันอีเมลของคุณคือ: {code}

รหัสนี้มีอายุ 10 นาที
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

        elif path in ("/get-customer", "/landing/get-customer"):
            email = data.get("email", "")
            if not email:
                self._json_response(400, {"error": "กรุณากรอกอีเมล", "found": False})
                return
            customer = get_customer_by_email(email)
            if customer:
                self._json_response(200, {"found": True, "data": customer})
            else:
                self._json_response(200, {"found": False, "data": {}})

        elif path in ("/verify-code", "/landing/verify-code"):
            email = data.get("email", "")
            code = data.get("code", "")
            if not email or not code:
                self._json_response(400, {"error": "กรุณากรอกอีเมลและรหัสยืนยัน"})
                return

            ok, msg = verify_code(email, code)
            if ok:
                self._json_response(200, {"status": "verified", "message": msg})
            else:
                self._json_response(400, {"error": msg})
        else:
            self._json_response(404, {"error": "Not found"})

    def do_GET(self):
        if self.path in ["/", "/health", "/ping"]:
            self._json_response(200, {"status": "ok", "service": "Landing Receiver"})
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        pass


def main():
    server = HTTPServer(("0.0.0.0", PORT), LandingHandler)
    print(f"[LANDING] Receiver on port {PORT}")
    print(f"[LANDING] Endpoints: /save, /send-code, /verify-code")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOPPED]")
        server.server_close()


if __name__ == "__main__":
    main()
