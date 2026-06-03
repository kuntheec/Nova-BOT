#!/usr/bin/env python3
"""
Admin Dashboard — The Global Manpower Immigration System
แสดงสรุปลูกค้า, เคส, สถานะ
"""

import json, os, datetime, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

CUSTOMERS_DB = r"D:\ImmigrationCases\_Customers.json"
LEADS_FILE = r"D:\ImmigrationCases\_leads.json"
IMMIGRATION_DIR = r"D:\ImmigrationCases"
PORT = 5004


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_customer_folders():
    """Scan ImmigrationCases for customer folders"""
    folders = []
    for item in os.listdir(IMMIGRATION_DIR):
        fpath = os.path.join(IMMIGRATION_DIR, item)
        if os.path.isdir(fpath) and not item.startswith("_"):
            folders.append(item)
    return sorted(folders)


def scan_customer_activity(cust_id):
    """Get message count and last activity for a customer"""
    cust_dir = os.path.join(IMMIGRATION_DIR, cust_id)
    if not os.path.exists(cust_dir):
        return {"total_files": 0, "total_size_kb": 0, "last_activity": "", "folders": []}

    dates = []
    total_files = 0
    total_size = 0

    for d in sorted(os.listdir(cust_dir)):
        dpath = os.path.join(cust_dir, d)
        if os.path.isdir(dpath):
            files = [f for f in os.listdir(dpath) if os.path.isfile(os.path.join(dpath, f))]
            if files:
                dates.append(d)
                total_files += len(files)
                total_size += sum(os.path.getsize(os.path.join(dpath, f)) for f in files)

    return {
        "total_files": total_files,
        "total_size_kb": round(total_size / 1024, 1),
        "last_activity": dates[-1] if dates else "",
        "date_count": len(dates)
    }


HTML = """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Dashboard — The Global Manpower</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f1f5f9; color: #1e293b; padding: 20px;
}
.header {
    background: #1e293b; color: #fff; padding: 20px 30px;
    border-radius: 12px; margin-bottom: 24px;
    display: flex; justify-content: space-between; align-items: center;
}
.header h1 { font-size: 22px; }
.header span { color: #94a3b8; font-size: 14px; }
.stats-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; margin-bottom: 24px;
}
.stat-card {
    background: #fff; padding: 18px 20px; border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.stat-card .num { font-size: 28px; font-weight: 700; color: #2563eb; }
.stat-card .label { font-size: 13px; color: #64748b; margin-top: 4px; }
.customer-card {
    background: #fff; border-radius: 12px; padding: 20px;
    margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    transition: box-shadow 0.2s;
}
.customer-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.customer-card .name {
    font-size: 17px; font-weight: 600; margin-bottom: 8px;
}
.customer-card .detail {
    font-size: 13px; color: #64748b; line-height: 1.8;
}
.customer-card .detail span { color: #334155; font-weight: 500; }
.badge {
    display: inline-block; padding: 2px 10px; border-radius: 20px;
    font-size: 12px; font-weight: 500; margin-left: 8px;
}
.badge-new { background: #dbeafe; color: #1d4ed8; }
.badge-active { background: #dcfce7; color: #16a34a; }
.badge-pending { background: #fef9c3; color: #a16207; }
.channels {
    display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px;
}
.channel-tag {
    display: inline-block; padding: 2px 8px; border-radius: 6px;
    font-size: 11px; background: #f1f5f9; color: #475569;
}
.activity-bar {
    display: flex; align-items: center; gap: 16px; margin-top: 10px;
    padding-top: 10px; border-top: 1px solid #f1f5f9;
    font-size: 12px; color: #94a3b8;
}
.footer { text-align: center; font-size: 12px; color: #94a3b8; margin-top: 40px; padding: 20px; }
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>📊 The Global Manpower — Admin Dashboard</h1>
        <span>Immigration Case Management System</span>
    </div>
    <div id="clock" style="font-size:14px;color:#94a3b8;"></div>
</div>

<div class="stats-row" id="statsRow">
    <div class="stat-card"><div class="num" id="totalCustomers">0</div><div class="label">ลูกค้าทั้งหมด</div></div>
    <div class="stat-card"><div class="num" id="totalMessages">0</div><div class="label">ข้อความ/ไฟล์ทั้งหมด</div></div>
    <div class="stat-card"><div class="num" id="newToday">0</div><div class="label">ลงทะเบียนวันนี้</div></div>
    <div class="stat-card"><div class="num" id="channelsCount">0</div><div class="label">ช่องทางที่เชื่อม</div></div>
</div>

<div id="customerList"></div>

<div class="footer">
    Nova Immigration System | Data from D:\\ImmigrationCases | Updated in real-time
</div>

<script>
async function loadData() {
    try {
        const res = await fetch('/admin/api/data');
        if (!res.ok) throw new Error('Failed');
        const data = await res.json();

        document.getElementById('totalCustomers').textContent = data.stats.total_customers;
        document.getElementById('totalMessages').textContent = data.stats.total_files;
        document.getElementById('newToday').textContent = data.stats.new_today;
        document.getElementById('channelsCount').textContent = data.stats.channel_count;

        const list = document.getElementById('customerList');
        list.innerHTML = data.customers.map(c => {
            const chs = [];
            if (c.channels.messenger) chs.push('<span class="channel-tag">FB Messenger</span>');
            if (c.channels.whatsapp) chs.push('<span class="channel-tag">WhatsApp</span>');
            if (c.channels.line && c.channels.line.length) chs.push('<span class="channel-tag">LINE ('+c.channels.line.length+')</span>');
            if (c.profile.email) chs.push('<span class="channel-tag">Email</span>');

            const badge = c.is_new ? '<span class="badge badge-new">NEW</span>' : '';

            return `<div class="customer-card">
                <div class="name">${c.customerId} — ${c.profile.name} ${badge}</div>
                <div class="detail">
                    📞 <span>${c.profile.phone || '—'}</span> &nbsp;|&nbsp;
                    📧 <span>${c.profile.email || '—'}</span>
                </div>
                <div class="channels">${chs.join('')}</div>
                <div class="activity-bar">
                    📁 ${c.activity.total_files} ไฟล์ (${c.activity.total_size_kb} KB)
                    ${c.activity.last_activity ? '| 🕐 ล่าสุด: ' + c.activity.last_activity : ''}
                </div>
            </div>`;
        }).join('');
    } catch(e) {
        document.getElementById('customerList').innerHTML = '<p style="color:#dc2626;padding:20px;">❌ โหลดข้อมูลไม่สำเร็จ: '+e.message+'</p>';
    }
}

function updateClock() {
    const now = new Date();
    const nzt = now.toLocaleString('en-NZ', {timeZone:'Pacific/Auckland', hour:'2-digit', minute:'2-digit', second:'2-digit', year:'numeric', month:'short', day:'numeric'});
    document.getElementById('clock').textContent = '🕐 ' + nzt + ' NZT';
}

loadData();
updateClock();
setInterval(loadData, 15000);
setInterval(updateClock, 1000);
</script>
</body>
</html>"""


class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Tailscale strips /admin prefix, so /admin -> / and /admin/api/data -> /api/data
        path = self.path
        if path in ("/", "/admin", "/admin/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

        elif path in ("/api/data", "/admin/api/data"):
            self._send_json()

        elif self.path in ["/", "/health", "/ping"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "Admin Dashboard"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self):
        """Build and return JSON data for dashboard"""
        customers_db = load_json(CUSTOMERS_DB)
        leads = load_json(LEADS_FILE)
        folders = get_customer_folders()

        # Count today registrations
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        new_today = sum(1 for l in leads if l.get("submitted_at", "").startswith(today))

        total_files = 0
        customers_data = []

        for c in customers_db.get("customers", []):
            cid = c["customerId"]
            activity = scan_customer_activity(cid)
            total_files += activity["total_files"]

            is_new = False
            if c.get("createdAt", ""):
                is_new = c["createdAt"].startswith(today)

            customers_data.append({
                "customerId": cid,
                "profile": c["profile"],
                "channels": c["channels"],
                "activity": activity,
                "is_new": is_new
            })

        # Show leads without customer profile
        for lead in leads:
            email = lead.get("email", "")
            matched = any(c["profile"].get("email") == email for c in customers_db.get("customers", []))
            if not matched:
                total_files += 1

        data = {
            "stats": {
                "total_customers": len(customers_db.get("customers", [])),
                "total_files": total_files,
                "new_today": new_today,
                "channel_count": len(customers_db.get("customers_by_channel", {}))
            },
            "customers": customers_data,
            "leads_unmatched": len(leads) - sum(1 for c in customers_db.get("customers", []) if c["profile"].get("email"))
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass


def main():
    server = HTTPServer(("0.0.0.0", PORT), AdminHandler)
    print(f"[ADMIN] Dashboard on http://0.0.0.0:{PORT}/admin")
    print(f"[ADMIN] API on http://0.0.0.0:{PORT}/admin/api/data")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOPPED]")
        server.server_close()


if __name__ == "__main__":
    main()
