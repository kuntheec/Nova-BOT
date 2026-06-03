#!/usr/bin/env python3
"""Admin Dashboard v2 — with search, customer IDs, clickable detail view"""
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
    return {}

def get_customer_folders():
    folders = []
    for item in os.listdir(IMMIGRATION_DIR):
        fpath = os.path.join(IMMIGRATION_DIR, item)
        if os.path.isdir(fpath) and not item.startswith("_"):
            folders.append(item)
    return sorted(folders)

def scan_customer_activity(cust_id):
    cust_dir = os.path.join(IMMIGRATION_DIR, cust_id)
    if not os.path.exists(cust_dir):
        return {"total_files": 0, "total_size_kb": 0, "last_activity": "", "files": []}
    dates = []
    total_files = 0
    total_size = 0
    all_files = []
    for d in sorted(os.listdir(cust_dir)):
        dpath = os.path.join(cust_dir, d)
        if os.path.isdir(dpath):
            files = sorted([f for f in os.listdir(dpath) if os.path.isfile(os.path.join(dpath, f))])
            if files:
                dates.append(d)
                total_files += len(files)
                for f in files:
                    fp = os.path.join(dpath, f)
                    sz = os.path.getsize(fp)
                    total_size += sz
                    all_files.append({"name": f, "date": d, "size_kb": round(sz/1024, 1)})
    return {
        "total_files": total_files,
        "total_size_kb": round(total_size / 1024, 1),
        "last_activity": dates[-1] if dates else "",
        "date_count": len(dates),
        "files": all_files
    }

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Dashboard — The Global Manpower</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#1e293b;padding:20px}
.header{background:#1e293b;color:#fff;padding:20px 30px;border-radius:12px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:20px}.header span{color:#94a3b8;font-size:13px}
.search-bar{display:flex;gap:10px;margin-bottom:20px}
.search-bar input{flex:1;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;outline:none;background:#fff}
.search-bar input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,0.15)}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat-card{background:#fff;padding:16px 18px;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.stat-card .num{font-size:24px;font-weight:700;color:#2563eb}
.stat-card .label{font-size:12px;color:#64748b;margin-top:3px}
.case-type-summary{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.case-type-summary h3{font-size:14px;color:#64748b;margin-bottom:12px;font-weight:600}
.case-type-grid{display:flex;flex-wrap:wrap;gap:10px}
.case-type-item{background:#f8fafc;padding:8px 16px;border-radius:20px;font-size:13px}
.case-type-item .type-name{color:#334155;font-weight:500}
.case-type-item .type-count{color:#2563eb;font-weight:700;margin-left:8px}
.customer-card{background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08);cursor:pointer;transition:all 0.2s;border:2px solid transparent}
.customer-card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.12);border-color:#93c5fd}
.customer-card .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.customer-card .name{font-size:16px;font-weight:600}
.customer-card .cid{font-size:12px;color:#64748b;background:#f1f5f9;padding:2px 8px;border-radius:6px}
.customer-card .detail{font-size:13px;color:#64748b;line-height:1.7}
.customer-card .detail span{color:#334155;font-weight:500}
.channels{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.channel-tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;background:#f1f5f9;color:#475569}
.activity-bar{display:flex;gap:12px;margin-top:8px;padding-top:8px;border-top:1px solid #f1f5f9;font-size:11px;color:#94a3b8}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:500;margin-left:6px}
.badge-new{background:#dbeafe;color:#1d4ed8}
.no-result{text-align:center;padding:40px;color:#94a3b8;font-size:14px}
/* Detail View */
.detail-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:100;padding:20px;overflow-y:auto}
.detail-card{background:#fff;border-radius:16px;max-width:600px;margin:40px auto;padding:30px}
.detail-card h2{font-size:18px;margin-bottom:4px}
.detail-card .close{float:right;background:none;border:none;font-size:24px;cursor:pointer;color:#94a3b8;padding:4px 8px}
.detail-card .close:hover{color:#334155}
.detail-section{margin-top:16px}
.detail-section h3{font-size:13px;color:#64748b;margin-bottom:8px;font-weight:600}
.detail-table{width:100%;border-collapse:collapse;font-size:12px}
.detail-table td{padding:6px 4px;border-bottom:1px solid #f1f5f9}
.detail-table td:first-child{color:#64748b;width:100px}
.detail-table td:last-child{color:#334155;font-weight:500}
.file-list{font-size:12px;max-height:200px;overflow-y:auto}
.file-item{padding:5px 0;border-bottom:1px solid #f1f5f9;display:flex;justify-content:space-between}
.file-item .fname{color:#334155}.file-item .fsize{color:#94a3b8}
.lead-box{background:#f8fafc;border-radius:8px;padding:12px;font-size:12px;line-height:1.7;margin-top:8px}
.lead-box .lb-label{color:#64748b}.lead-box .lb-val{color:#334155;font-weight:500}
.footer{text-align:center;font-size:11px;color:#94a3b8;margin-top:30px;padding:20px}
</style>
</head>
<body>

<div class="header">
  <div><h1>Admin Dashboard</h1><span>The Global Manpower Immigration System</span></div>
  <div id="clock" style="font-size:13px;color:#94a3b8;"></div>
</div>

<div class="search-bar">
  <input type="text" id="searchInput" placeholder="Search by name, email, phone, ID..." onkeyup="filterCustomers()">
  <span style="font-size:12px;color:#94a3b8;align-self:center;white-space:nowrap" id="resultCount"></span>
</div>

<div class="stats-row" id="statsRow">
  <div class="stat-card"><div class="num" id="totalCustomers">0</div><div class="label">Customers</div></div>
  <div class="stat-card"><div class="num" id="totalMessages">0</div><div class="label">Files</div></div>
  <div class="stat-card"><div class="num" id="newToday">0</div><div class="label">New Today</div></div>
  <div class="stat-card"><div class="num" id="caseTypes">0</div><div class="label">Case Types</div></div>
</div>

<!-- Case Type Summary Window -->
<div class="case-type-summary" id="caseTypeSummary">
  <h3>📊 Customers by Case Type</h3>
  <div class="case-type-grid" id="caseTypeGrid">
    <span style="font-size:12px;color:#94a3b8;">Loading...</span>
  </div>
</div>

<div id="customerList"></div>
<div class="footer">Nova Immigration System | Real-time data</div>

<!-- Detail Overlay -->
<div class="detail-overlay" id="detailOverlay" onclick="if(event.target===this)closeDetail()">
  <div class="detail-card" id="detailCard">
    <button class="close" onclick="closeDetail()">×</button>
    <h2 id="detailName"></h2>
    <span class="cid" id="detailId"></span>
    <div id="detailBody"></div>
  </div>
</div>

<script>
let customersData = [];
let currentLang = 'en';

function switchLang(l){currentLang=l;document.querySelectorAll('.lang-btn').forEach(b=>b.classList.toggle('active',b.dataset.lang===l))}

async function loadData(){
  try{
    const r=await fetch('/admin/api/data');if(!r.ok)throw Error();
    const d=await r.json();
    customersData=d.customers;
    const s=d.stats;
    document.getElementById('totalCustomers').textContent=s.total_customers;
    document.getElementById('totalMessages').textContent=s.total_files;
    document.getElementById('newToday').textContent=s.new_today;
    document.getElementById('caseTypes').textContent=s.case_types;
    
    // Render case type summary
    renderCaseTypeSummary(s.case_type_counts || {});
    
    renderCustomers(d.customers);
  }catch(e){document.getElementById('customerList').innerHTML='<div class="no-result">Failed to load data</div>'}
}

function renderCaseTypeSummary(caseTypeCounts){
  const container = document.getElementById('caseTypeGrid');
  const types = Object.keys(caseTypeCounts);
  if(types.length === 0){
    container.innerHTML = '<span style="font-size:12px;color:#94a3b8;">No case types assigned</span>';
    return;
  }
  
  // Sort by count descending
  types.sort((a,b) => caseTypeCounts[b] - caseTypeCounts[a]);
  
  container.innerHTML = types.map(type => `
    <div class="case-type-item">
      <span class="type-name">${escapeHtml(type)}</span>
      <span class="type-count">${caseTypeCounts[type]}</span>
    </div>
  `).join('');
}

function escapeHtml(str){
  if(!str) return '';
  return str.replace(/[&<>]/g, function(m){
    if(m === '&') return '&amp;';
    if(m === '<') return '&lt;';
    if(m === '>') return '&gt;';
    return m;
  });
}

function renderCustomers(list){
  const el=document.getElementById('customerList');
  const search=document.getElementById('searchInput').value.toLowerCase().trim();
  const filtered=search?list.filter(c=>{
    const p=c.profile;
    const q=search;
    return (p.name||'').toLowerCase().includes(q)
        || (p.email||'').toLowerCase().includes(q)
        || (p.phone||'').includes(q)
        || (c.displayId||'').toLowerCase().includes(q)
        || (c.customerId||'').toLowerCase().includes(q);
  }):list;

  document.getElementById('resultCount').textContent=filtered.length+' / '+list.length;

  if(!filtered.length){
    el.innerHTML='<div class="no-result">No customers found</div>';
    return;
  }

  el.innerHTML=filtered.map(c=>{
    const p=c.profile,ch=c.channels;
    const chs=[];
    if(ch.messenger)chs.push('<span class="channel-tag">FB Messenger</span>');
    if(ch.whatsapp)chs.push('<span class="channel-tag">WhatsApp</span>');
    if(ch.line&&ch.line.length)chs.push('<span class="channel-tag">LINE ('+ch.line.length+')</span>');
    if(p.email)chs.push('<span class="channel-tag">Email</span>');
    const badge=c.is_new?'<span class="badge badge-new">NEW</span>':'';
    const act=c.activity;
    return '<div class="customer-card" onclick="showDetail(\\''+c.customerId+'\\')">'
      +'<div class="top"><div class="name">'+escapeHtml(p.name)+' '+badge+'</div><div class="cid">'+(c.displayId||c.customerId)+'</div></div>'
      +'<div class="detail">📞 <span>'+(p.phone||'—')+'</span> &nbsp;📧 <span>'+(p.email||'—')+'</span></div>'
      +'<div class="channels">'+chs.join('')+'</div>'
      + (c.topic ? '<div class="detail" style="margin-top:4px;font-size:12px;color:#2563eb">Topic: ' + escapeHtml(c.topic) + '</div>' : '')
      +'<div class="activity-bar">📁 '+act.total_files+' files ('+act.total_size_kb+' KB)'+(act.last_activity?' | '+act.last_activity:'')+'</div>'
      +'</div>';
  }).join('');
}

function filterCustomers(){renderCustomers(customersData)}

async function showDetail(custId){
  try{
    const r=await fetch('/admin/api/customer/'+custId);if(!r.ok)throw Error();
    const d=await r.json();
    const c=d.customer,p=c.profile,ch=c.channels,act=d.activity;
    document.getElementById('detailName').textContent=p.name;
    document.getElementById('detailId').textContent=c.displayId||c.customerId;
    
    let html='<div class="detail-section"><h3>Profile</h3><table class="detail-table">'
      +'<tr><td>Phone</td><td>'+(p.phone||'—')+'</td></tr>'
      +'<tr><td>Email</td><td>'+(p.email||'—')+'</td></tr>'
      +'<tr><td>Channels</td><td>';
    if(ch.messenger)html+='FB: '+escapeHtml(ch.messenger)+'<br>';
    if(ch.whatsapp)html+='WA: '+escapeHtml(ch.whatsapp)+'<br>';
    if(ch.line)html+='LINE: '+ch.line.join(', ')+'<br>';
    html+='</td></tr></table></div>';

    // Lead info
    if(d.lead){
      const l=d.lead;
      html+='<div class="detail-section"><h3>Registration Info</h3><div class="lead-box">'
        +'<span class="lb-label">Submitted:</span> <span class="lb-val">'+(l.submitted_at||'')+'</span><br>';
      if(l.topic)html+='<span class="lb-label">Topic:</span> <span class="lb-val">'+escapeHtml(l.topic)+'</span><br>';
      if(l.customer_type)html+='<span class="lb-label">Type:</span> <span class="lb-val">'+escapeHtml(l.customer_type)+'</span>';
      html+='</div></div>';
    }

    // Files
    if(act.files&&act.files.length){
      html+='<div class="detail-section"><h3>Files ('+act.files.length+')</h3><div class="file-list">';
      act.files.slice().reverse().slice(0,30).forEach(f=>{
        html+='<div class="file-item"><span class="fname">'+f.date+' — '+escapeHtml(f.name)+'</span><span class="fsize">'+f.size_kb+' KB</span></div>';
      });
      html+='</div></div>';
    }

    document.getElementById('detailBody').innerHTML=html;
    document.getElementById('detailOverlay').style.display='block';
  }catch(e){
    document.getElementById('detailBody').innerHTML='<div class="no-result">Error loading details</div>';
    document.getElementById('detailOverlay').style.display='block';
  }
}

function closeDetail(){document.getElementById('detailOverlay').style.display='none'}

function updateClock(){
  const n=new Date();
  document.getElementById('clock').textContent=n.toLocaleString('en-NZ',{timeZone:'Pacific/Auckland',hour:'2-digit',minute:'2-digit',second:'2-digit',day:'numeric',month:'short'})+' NZT';
}
loadData();updateClock();
setInterval(loadData,15000);
setInterval(updateClock,1000);
</script>
</body>
</html>"""

class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path
        if path in ("/", "/admin", "/admin/"):
            self._html_response(HTML)
        elif path in ("/api/data", "/admin/api/data"):
            self._send_json()
        elif path.startswith("/api/customer/") or path.startswith("/admin/api/customer/"):
            cust_id = path.rstrip("/").split("/")[-1]
            self._send_customer_detail(cust_id)
        else:
            self.send_response(404); self.end_headers()

    def _send_json(self):
        db = load_json(CUSTOMERS_DB)
        leads_data = load_json(LEADS_FILE)
        leads_list = leads_data if isinstance(leads_data, list) else []
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        new_today = 0
        total_files = 0
        case_type_counts = {}  # Changed from set to dict for counting
        customers_data = []

        # Build email -> topic mapping from leads
        email_to_topic = {}
        for lead in leads_list:
            email = lead.get("email")
            topic = lead.get("topic", "")
            if email and topic:
                email_to_topic[email] = topic

        for c in db.get("customers", []):
            cid = c["customerId"]
            activity = scan_customer_activity(cid)
            total_files += activity["total_files"]
            is_new = c.get("createdAt", "").startswith(today) if c.get("createdAt") else False
            
            # Get topic from leads using email
            customer_email = c["profile"].get("email", "")
            topic = email_to_topic.get(customer_email, "")
            
            # Count case types
            if topic:
                case_type_counts[topic] = case_type_counts.get(topic, 0) + 1
            
            customers_data.append({
                "customerId": cid,
                "displayId": c.get("displayId", ""),
                "profile": c["profile"],
                "channels": c["channels"],
                "activity": activity,
                "is_new": is_new,
                "topic": topic
            })
            
        # Count new leads today
        for lead in leads_list:
            if lead.get("submitted_at", "").startswith(today):
                new_today += 1

        data = {
            "stats": {
                "total_customers": len(db.get("customers", [])),
                "total_files": total_files,
                "new_today": new_today,
                "case_types": len(case_type_counts),  # Number of unique case types
                "case_type_counts": case_type_counts  # NEW: counts per case type
            },
            "customers": customers_data
        }
        self._json_response(200, data)

    def _send_customer_detail(self, cust_id):
        db = load_json(CUSTOMERS_DB)
        leads = load_json(LEADS_FILE) if isinstance(load_json(LEADS_FILE), list) else []
        customer = None
        for c in db.get("customers", []):
            if c.get("customerId") == cust_id or c.get("displayId") == cust_id:
                customer = c; break
        if not customer:
            self._json_response(404, {"error": "Not found"}); return
        # Use customerId (folder name) for activity scan
        folder_name = customer["customerId"]
        activity = scan_customer_activity(folder_name)
        lead_info = None
        for lead in leads:
            if lead.get("email") == customer["profile"].get("email"):
                lead_info = lead; break
        self._json_response(200, {"customer": customer, "activity": activity, "lead": lead_info})

    def _html_response(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args): pass

if __name__ == "__main__":
    s = HTTPServer(("0.0.0.0", PORT), AdminHandler)
    print(f"[ADMIN] Dashboard v2 on port {PORT}")
    try: s.serve_forever()
    except KeyboardInterrupt: s.server_close()
