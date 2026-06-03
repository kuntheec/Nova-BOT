#!/usr/bin/env python3
"""
Landing Page — Local Receiver
รับข้อมูลจากลูกค้าที่กรอกฟอร์ม แล้วบันทึก + สร้าง Customer Profile
"""

import json, os, datetime, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = r"D:\ImmigrationCases"
LEADS_FILE = os.path.join(BASE_DIR, "_leads.json")
PORT = 5003

os.makedirs(BASE_DIR, exist_ok=True)


def load_leads():
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_leads(leads):
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


def add_or_update_customer(data):
    """Add lead to DB and create/update customer profile"""
    leads = load_leads()
    
    entry = {
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "line_id": data.get("line_id", ""),
        "messenger_id": data.get("messenger_id", ""),
        "whatsapp": data.get("whatsapp", ""),
        "topic": data.get("topic", ""),
        "source": "landing_page",
        "submitted_at": datetime.datetime.now().isoformat()
    }
    
    # Check if email already exists
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
    
    # Also create/update customer in consolidate system
    line_ids = [entry["line_id"]] if entry.get("line_id") else []
    # Import consolidate module
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


class LandingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Tailscale strips path prefix, so /landing/save arrives as /save
        if self.path in ("/landing/save", "/save"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            
            print(f"\n[LANDING] Received registration from {data.get('name')}")
            entry = add_or_update_customer(data)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "received"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path in ["/", "/health", "/ping"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "Landing Receiver"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    server = HTTPServer(("0.0.0.0", PORT), LandingHandler)
    print(f"[LANDING] Receiver on port {PORT}")
    print(f"[LANDING] Save to {LEADS_FILE}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOPPED]")
        server.server_close()


if __name__ == "__main__":
    main()
