#!/usr/bin/env python3
"""
Landing Page — Local Receiver v3
รับข้อมูลจากลูกค้า + Family Member System
Customer ID (by email) → Multiple Individual IDs
"""

import json, os, datetime, sys, random, pickle, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
import base64

BASE_DIR = r"D:\ImmigrationCases"
LEADS_FILE = os.path.join(BASE_DIR, "_leads.json")
CODES_FILE = os.path.join(BASE_DIR, "_verify_codes.json")
PORT = 5003

os.makedirs(BASE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# NEW DATA MODEL
# _Customers.json v2:
# {
#   "customers": [
#     {
#       "customerId": "C003",
#       "displayId": "C003",
#       "profile": { "name": "...", "email": "...", "phone": "..." },
#       "channels": { "messenger": "", "whatsapp": "", "line": [] },
#       "individuals": [
#         { "individualId": "I001", "name": "...", "relationship": "self",
#           "phone": "...", "topic": "...", "created_at": "..." },
#         { "individualId": "I002", "name": "...", "relationship": "spouse",
#           "phone": "...", "topic": "...", "created_at": "..." }
#       ],
#       "createdAt": "...", "updatedAt": "..."
#     }
#   ],
#   "customers_by_channel": {}
# }
# ═══════════════════════════════════════════════════════════

CUSTOMERS_DB = os.path.join(BASE_DIR, "_Customers.json")


# ── Customer DB (v2) ─────────────────────────────────────

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
        for k in ["messenger", "whatsapp"]:
            v = ch.get(k, "")
            if v:
                db["customers_by_channel"][f"{k}:{v}"] = c["customerId"]
        for lid in ch.get("line", []):
            if lid:
                db["customers_by_channel"][f"line:{lid}"] = c["customerId"]
        email = c.get("profile", {}).get("email", "")
        if email:
            db["customers_by_channel"][f"email:{email}"] = c["customerId"]
    db["last_updated"] = datetime.datetime.now().isoformat()
    with open(CUSTOMERS_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def next_customer_id(db):
    existing = set()
    for c in db.get("customers", []):
        if c.get("customerId", "").startswith("C"):
            try:
                existing.add(int(c["customerId"][1:]))
            except: pass
        if c.get("displayId", "").startswith("C"):
            try:
                existing.add(int(c["displayId"][1:]))
            except: pass
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
            except: pass
    n = 1
    while n in existing:
        n += 1
    return f"I{n:03d}"


def get_customer_by_email(db, email):
    """Find customer record by email"""
    email_lower = email.lower().strip()
    for c in db.get("customers", []):
        if c.get("profile", {}).get("email", "").lower().strip() == email_lower:
            return c
    return None

def get_or_create_customer_by_email(db, email, name, phone):
    """Find existing customer by email, or create new one"""
    c = get_customer_by_email(db, email)
    if c:
        return c, False  # existing
    # Create new customer
    cid = next_customer_id(db)
    new_cust = {
        "customerId": cid,
        "displayId": cid,
        "profile": {
            "name": name,
            "phone": phone,
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
    db["customers"].append(new_cust)
    return new_cust, True  # new


def find_individual(customer, individual_id):
    """Find individual by ID within a customer"""
    for ind in customer.get("individuals", []):
        if ind.get("individualId") == individual_id:
            return ind
    return None

def get_or_create_individual(customer, individual_id, name, phone, topic, relationship="self"):
    """Get existing individual or create new one"""
    if individual_id:
        ind = find_individual(customer, individual_id)
        if ind:
            # Update existing
            ind["name"] = name
            if phone:
                ind["phone"] = phone
            if topic:
                ind["topic"] = topic
            ind["updated_at"] = datetime.datetime.now().isoformat()
            return ind, False
    # Create new
    iid = next_individual_id(customer)
    new_ind = {
        "individualId": iid,
        "name": name,
        "phone": phone,
        "relationship": relationship,
        "topic": topic,
        "created_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat()
    }
    customer["individuals"].append(new_ind)
    return new_ind, True


def submit_lead(data):
    """Main entry: create/update customer + individual from form submission"""
    db = load_customers()
    
    email = data.get("email", "").lower().strip()
    name = data.get("name", "")
    phone = data.get("phone", "")
    topic = data.get("topic", "")
    individual_id = data.get("individual_id", "")  # If editing an existing individual
    relationship = data.get("relationship", "self")
    
    # Get or create customer
    customer, is_new_customer = get_or_create_customer_by_email(db, email, name, phone)
    
    # Update customer profile with latest contact info
    # But DON'T overwrite if this is a family member (different name)
    # The profile holds the primary/main contact name
    if data.get("customer_type") == "new" or not customer["individuals"]:
        customer["profile"]["name"] = name
    
    # Update channels
    if data.get("line_id"):
        lids = customer["channels"].get("line", [])
        if data["line_id"] not in lids:
            lids.append(data["line_id"])
    if data.get("messenger_id"):
        customer["channels"]["messenger"] = data["messenger_id"]
    if data.get("whatsapp"):
        customer["channels"]["whatsapp"] = data["whatsapp"]
    customer["profile"]["phone"] = phone
    customer["updatedAt"] = datetime.datetime.now().isoformat()
    
    # Get or create individual
    individual, is_new_individual = get_or_create_individual(
        customer, individual_id, name, phone, topic, relationship
    )
    
    save_customers(db)
    
    # Also save to _leads.json for backward compatibility
    _save_lead_backup(data, individual, is_new_individual)
    
    # Sync to consolidate_messages
    _sync_to_consolidate(data, customer)
    
    print(f"[LEAD] {'New' if is_new_customer else 'Existing'} customer {customer['customerId']} | "
          f"{'New' if is_new_individual else 'Updated'} individual {individual['individualId']} - {name}")
    
    return {
        "customer_id": customer["customerId"],
        "display_id": customer.get("displayId", customer["customerId"]),
        "individual_id": individual["individualId"],
        "is_new_customer": is_new_customer,
        "is_new_individual": is_new_individual
    }


def _save_lead_backup(data, individual, is_new):
    """Save to _leads.json for backward compatibility"""
    leads = []
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            leads = json.load(f) if isinstance(json.load(f), list) else []
    entry = {
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "line_id": data.get("line_id", ""),
        "messenger_id": data.get("messenger_id", ""),
        "whatsapp": data.get("whatsapp", ""),
        "topic": data.get("topic", ""),
        "relationship": data.get("relationship", "self"),
        "individual_id": individual["individualId"],
        "email_verified": True,
        "source": "landing_page",
        "customer_type": data.get("customer_type", "new"),
        "submitted_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat()
    }
    # Check if this email+individual combination exists
    found = False
    for lead in leads:
        if (lead.get("email", "").lower() == entry["email"].lower()
                and lead.get("individual_id") == entry["individual_id"]):
            lead.update(entry)
            found = True
            break
    if not found:
        leads.append(entry)
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


def _sync_to_consolidate(data, customer):
    """Sync new channels to consolidate_messages system"""
    line_ids = [data["line_id"]] if data.get("line_id") else []
    sys.path.insert(0, r"D:\OpenClawData\workspace")
    try:
        import consolidate_messages
        # Update existing customer with new channel info
        consolidate_messages.add_customer(
            name=customer["profile"]["name"],
            phone=customer["profile"]["phone"],
            email=customer["profile"]["email"],
            messenger_id=customer["channels"].get("messenger", ""),
            whatsapp_num=customer["channels"].get("whatsapp", ""),
            line_ids=line_ids
        )
    except Exception as e:
        print(f"[CUSTOMER] Sync error: {e}")


# ── API: Get customer info for existing customer ─────────

def get_customer_full_info(email):
    """Get full customer info + all individuals for the landing page"""
    db = load_customers()
    customer = get_customer_by_email(db, email)
    if not customer:
        return None
    
    # Get lead info (for topic, etc.)
    leads = []
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            leads = json.load(f) if isinstance(load_leads(), list) else []
    
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


# ── Verification Codes ──────────────────────────────────

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


# ── Send Email via Gmail API ────────────────────────────

def send_email(to_email, subject, body):
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


def load_leads():
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ── HTTP Handler ────────────────────────────────────────

class LandingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode("utf-8"))

        # Tailscale strips /landing prefix
        path = self.path.replace("/landing", "")

        if path == "/submit":
            print(f"\n[LANDING] Submission from {data.get('name')} ({data.get('email')})")
            result = submit_lead(data)
            self._json_response(200, {"status": "received", "data": result})

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
            print(f"[DEBUG] send_email returned: {sent} (type: {type(sent)})")  # ← เพิ่มบรรทัดนี้
            if sent:
                self._json_response(200, {"status": "sent", "message": "ส่งรหัสยืนยันไปยังอีเมลของคุณแล้ว"})
            else:
                self._json_response(500, {"error": "ไม่สามารถส่งอีเมลได้ กรุณาลองใหม่อีกครั้ง"})

        elif path == "/verify-code":
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

        elif path == "/get-customer":
            email = data.get("email", "")
            if not email:
                self._json_response(400, {"error": "กรุณากรอกอีเมล", "found": False})
                return

            # First check new Customer DB (v2)
            info = get_customer_full_info(email)
            if info:
                self._json_response(200, {"found": True, "data": info, "db_version": "v2"})
                return

            # Fallback: check old _leads.json
            leads = load_leads()
            for lead in leads:
                if lead.get("email", "").lower() == email.lower():
                    self._json_response(200, {
                        "found": True,
                        "data": {
                            "name": lead.get("name", ""),
                            "phone": lead.get("phone", ""),
                            "email": lead.get("email", ""),
                            "line_id": lead.get("line_id", ""),
                            "messenger_id": lead.get("messenger_id", ""),
                            "whatsapp": lead.get("whatsapp", ""),
                            "topic": lead.get("topic", ""),
                            "individuals": []
                        },
                        "db_version": "v1"
                    })
                    return

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
            """Get individual details for editing"""
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
            ind = find_individual(customer, individual_id)
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
            self._json_response(200, {"status": "ok", "service": "Landing Receiver v3"})
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
    print("  Landing Page Receiver v3")
    print("  Family Member System Active")
    print("=" * 50)
    server = HTTPServer(("0.0.0.0", PORT), LandingHandler)
    print(f"[LANDING] Receiver on port {PORT}")
    print(f"[LANDING] Endpoints: /submit, /send-code, /verify-code, /get-customer, /get-family, /get-individual")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOPPED]")
        server.server_close()


if __name__ == "__main__":
    main()
