#!/usr/bin/env python3
"""Admin Dashboard v3 — with Individuals, Case Type Customer Counts
Fixes: Issue #1 – Use displayId for folder scanning; Issue #2 – New Today count bug.
"""

import json, os, datetime, sys, collections, urllib.parse, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
load_dotenv()

# Configurable paths
BASE_DIR = os.getenv("BASE_DIR", r"D:\ImmigrationCases")
CUSTOMERS_DB = os.getenv("CUSTOMERS_DB", os.path.join(BASE_DIR, "_Customers.json"))
LEADS_FILE = os.getenv("LEADS_FILE", os.path.join(BASE_DIR, "_leads.json"))
PORT = int(os.getenv("ADMIN_PORT", "5004"))

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def scan_customer_activity(folder_id):
    """Scan folder by displayId (or customerId)."""
    cust_dir = os.path.join(BASE_DIR, folder_id)
    if not os.path.exists(cust_dir):
        return {"total_files": 0, "total_size_kb": 0, "last_activity": "", "files": []}
    all_files = []
    total_size = 0
    latest_mtime = 0
    latest_date_str = ""
    for root, dirs, files in os.walk(cust_dir):
        for f in files:
            if f.endswith('.meta') or f.endswith('.ocr.txt'):
                continue
            filepath = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(filepath)
                size = os.path.getsize(filepath)
            except OSError:
                continue
            total_size += size
            rel_path = os.path.relpath(filepath, cust_dir)
            parts = rel_path.split(os.sep)
            date_str = ""
            for part in parts:
                if re.match(r'^\d{4}-\d{2}-\d{2}$', part):
                    date_str = part
                    break
            if not date_str:
                date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_date_str = date_str
            all_files.append({
                "name": f,
                "date": date_str,
                "size_kb": round(size / 1024, 1),
                "path": rel_path
            })
    if latest_mtime > 0:
        last_activity = latest_date_str
    else:
        last_activity = ""
    return {
        "total_files": len(all_files),
        "total_size_kb": round(total_size / 1024, 1),
        "last_activity": last_activity,
        "date_count": len(set(f["date"] for f in all_files)),
        "files": all_files
    }

def get_case_type_summary(db, leads_list):
    type_customers = collections.defaultdict(set)
    if isinstance(leads_list, list):
        for lead in leads_list:
            topic = lead.get("topic", "")
            email = lead.get("email", "").lower().strip()
            if topic:
                for c in db.get("customers", []):
                    if c.get("profile", {}).get("email", "").lower().strip() == email:
                        cid = c.get("displayId") or c.get("customerId")
                        type_customers[topic].add(cid)
                        break
    return sorted(
        [{"type": t.replace("_", " ").title(), "count": len(ids), "customers": list(ids)}
         for t, ids in type_customers.items()],
        key=lambda x: -x["count"]
    )

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
.case-type-section{background:#fff;border-radius:10px;padding:16px 18px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.case-type-section h3{font-size:13px;color:#64748b;margin-bottom:10px;font-weight:600}
.case-type-bar{display:flex;flex-wrap:wrap;gap:8px}
.case-type-item{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;flex:1;min-width:140px;text-align:center;cursor:pointer;transition:all 0.2s}
.case-type-item:hover{border-color:#93c5fd;background:#eff6ff}
.case-type-item .ct-name{font-size:12px;color:#64748b}
.case-type-item .ct-count{font-size:22px;font-weight:700;color:#2563eb;margin:4px 0}
.case-type-item .ct-label{font-size:10px;color:#94a3b8}
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
.ind-box{background:#f0fdf4;border-radius:8px;padding:10px 12px;font-size:12px;line-height:1.6;margin-top:6px}
.ind-box .ind-label{color:#16a34a;font-weight:600;font-size:11px}
.ind-box .ind-val{color:#334155}
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
  <div class="stat-card"><div class="num" id="totalCustomers">0</div><div class="label">Customers (Families)</div></div>
  <div class="stat-card"><div class="num" id="totalIndividuals">0</div><div class="label">Individuals</div></div>
  <div class="stat-card"><div class="num" id="totalMessages">0</div><div class="label">Files</div></div>
  <div class="stat-card"><div class="num" id="newToday">0</div><div class="label">New Today</div></div>
</div>

<div class="case-type-section" id="caseTypeSection">
  <h3>📊 Customers by Case Type</h3>
  <div class="case-type-bar" id="caseTypeBar"></div>
</div>

<div id="customerList"></div>
<div class="footer">Nova Immigration System v3 | Family Members | Real-time data</div>

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

async function loadData(){
  try{
    const r=await fetch('/admin/api/data');if(!r.ok)throw Error();
    const d=await r.json();
    customersData=d.customers;
    const s=d.stats;
    document.getElementById('totalCustomers').textContent=s.total_customers;
    document.getElementById('totalIndividuals').textContent=s.total_individuals;
    document.getElementById('totalMessages').textContent=s.total_files;
    document.getElementById('newToday').textContent=s.new_today;
    renderCaseTypes(d.case_types);
    renderCustomers(d.customers);
  }catch(e){document.getElementById('customerList').innerHTML='<div class="no-result">Failed to load data</div>'}
}

function renderCaseTypes(types){
  const el=document.getElementById('caseTypeBar');
  if(!types||!types.length){
    el.innerHTML='<div style="font-size:12px;color:#94a3b8">No case type data yet</div>';
    return;
  }
  el.innerHTML=types.map(t=>{
    return '<div class="case-type-item" onclick="filterByCaseType(\\''+t.type+'\\')">'
      +'<div class="ct-name">'+t.type+'</div>'
      +'<div class="ct-count">'+t.count+'</div>'
      +'<div class="ct-label">customer'+(t.count>1?'s':'')+'</div>'
      +'</div>';
  }).join('');
}

let caseTypeFilter = null;

function filterByCaseType(type){
  caseTypeFilter=(caseTypeFilter===type)?null:type;
  renderCustomers(customersData);
}

function renderCustomers(list){
  const el=document.getElementById('customerList');
  const search=document.getElementById('searchInput').value.toLowerCase().trim();
  let filtered=list;
  if(caseTypeFilter){
    filtered=filtered.filter(c=>c.case_type&&c.case_type.toLowerCase().includes(caseTypeFilter.toLowerCase()));
    document.getElementById('searchInput').placeholder='Filtered: '+caseTypeFilter+' (click again to clear)';
  } else {
    document.getElementById('searchInput').placeholder='Search by name, email, phone, ID...';
  }
  if(search){
    filtered=filtered.filter(c=>{
      const p=c.profile;
      if((p.name||'').toLowerCase().includes(search))return true;
      if((p.email||'').toLowerCase().includes(search))return true;
      if((p.phone||'').includes(search))return true;
      if((c.displayId||'').toLowerCase().includes(search))return true;
      if((c.customerId||'').toLowerCase().includes(search))return true;
      if(c.individuals){
        for(const ind of c.individuals){
          if((ind.name||'').toLowerCase().includes(search))return true;
          if((ind.individualId||'').toLowerCase().includes(search))return true;
        }
      }
      return false;
    });
  }
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
    const indCount=c.individuals?c.individuals.length:1;
    return '<div class="customer-card" onclick="showDetail(\\''+c.customerId+'\\')">'
      +'<div class="top"><div class="name">'+p.name+' '+badge+'</div><div class="cid">'+(c.displayId||c.customerId)+'</div></div>'
      +'<div class="detail">📞 <span>'+(p.phone||'—')+'</span> &nbsp;📧 <span>'+(p.email||'—')+'</span></div>'
      +'<div class="detail" style="font-size:11px;color:#16a34a">👤 <strong>'+indCount+'</strong> individual'+(indCount>1?'s':'')+'</div>'
      +'<div class="channels">'+chs.join('')+'</div>'
      + (c.case_type ? '<div class="detail" style="margin-top:4px;font-size:12px;color:#2563eb">Topic: ' + c.case_type + '</div>' : '')
      +'<div class="activity-bar">📁 '+act.total_files+' files ('+act.total_size_kb+' KB)'+(act.last_activity?' | '+act.last_activity:'')+'</div>'
      +'</div>';
  }).join('');
}

function filterCustomers(){caseTypeFilter=null;renderCustomers(customersData)}

async function showDetail(custId){
  try{
    const r=await fetch('/admin/api/customer/'+custId);if(!r.ok)throw Error();
    const d=await r.json();
    const c=d.customer,p=c.profile,ch=c.channels,act=d.activity;
    document.getElementById('detailName').textContent=p.name;
    document.getElementById('detailId').textContent=c.displayId||c.customerId;
    let html='<div class="detail-section"><h3>Profile</h3><table class="detail-table">'
      +'<tr><td>Phone<\/td><td>'+(p.phone||'—')+'<\/td><\/tr>'
      +'<tr><td>Email<\/td><td>'+(p.email||'—')+'<\/td><\/tr>'
      +'<tr><td>Channels<\/td><td>';
    if(ch.messenger)html+='FB: '+ch.messenger+'<br>';
    if(ch.whatsapp)html+='WA: '+ch.whatsapp+'<br>';
    if(ch.line)html+='LINE: '+ch.line.join(', ')+'<br>';
    html+='<\/td><\/tr><\/table><\/div>';
    if(c.individuals&&c.individuals.length){
      html+='<div class="detail-section"><h3>👨‍👩‍👧‍👦 Individuals ('+c.individuals.length+')</h3>';
      c.individuals.forEach(ind=>{
        html+='<div class="ind-box">'
          +'<span class="ind-label">'+ind.individualId+'</span> | '
          +'<span class="ind-val">'+ind.name+'</span>'
          + (ind.relationship?' <span style="color:#64748b">('+ind.relationship+')</span>':'')
          +'<br>'
          + (ind.topic?'<span class="ind-label">Topic:</span> <span class="ind-val">'+ind.topic+'</span>':'')
          +'</div>';
      });
      html+='</div>';
    }
    if(d.lead){
      const l=d.lead;
      html+='<div class="detail-section"><h3>Registration Info</h3><div class="lead-box">'
        +'<span class="lb-label">Submitted:</span> <span class="lb-val">'+(l.submitted_at||'')+'</span><br>';
      if(l.topic)html+='<span class="lb-label">Topic:</span> <span class="lb-val">'+l.topic+'</span><br>';
      if(l.customer_type)html+='<span class="lb-label">Type:</span> <span class="lb-val">'+l.customer_type+'</span>';
      html+='</div></div>';
    }
    if(act.files&&act.files.length){
      html+='<div class="detail-section"><h3>Files ('+act.files.length+')</h3><div class="file-list">';
      act.files.slice().reverse().slice(0,30).forEach(f=>{
        html+='<div class="file-item"><span class="fname">'+f.date+' — '+f.name+'</span><span class="fsize">'+f.size_kb+' KB</span></div>';
      });
      html+='</div></div>';
    }
    document.getElementById('detailBody').innerHTML=html;
    document.getElementById('detailOverlay').style.display='block';
  }catch(e){
    document.getElementById('detailBody').innerHTML='<div class="no-result">Error loading details: check folder/data</div>';
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
            cust_id = urllib.parse.unquote(path.rstrip("/").split("/")[-1])
            self._send_customer_detail(cust_id)
        else:
            self.send_response(404); self.end_headers()

    def _send_json(self):
        db = load_json(CUSTOMERS_DB)
        leads_data = load_json(LEADS_FILE)
        leads_list = leads_data if isinstance(leads_data, list) else []
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        # Issue #2 fix: count unique leads submitted today
        leads_today = set()
        for lead in leads_list:
            if lead.get("submitted_at", "").startswith(today):
                leads_today.add(lead.get("email", ""))
        new_today = len(leads_today)
        total_files = 0
        total_individuals = 0
        case_type_summary = get_case_type_summary(db, leads_list)
        customers_data = []
        for c in db.get("customers", []):
            # Issue #1 fix: use displayId for folder scanning
            folder_id = c.get("displayId") or c["customerId"]
            activity = scan_customer_activity(folder_id)
            total_files += activity["total_files"]
            is_new = c.get("createdAt", "").startswith(today) if c.get("createdAt") else False
            individuals = c.get("individuals", [])
            total_individuals += len(individuals) if individuals else 1
            case_type = ""
            if individuals:
                for ind in individuals:
                    if ind.get("relationship") in ("self", ""):
                        case_type = ind.get("topic", "")
                        break
                if not case_type and individuals:
                    case_type = individuals[0].get("topic", "")
            customers_data.append({
                "customerId": c["customerId"],
                "displayId": c.get("displayId", ""),
                "profile": c["profile"],
                "channels": c["channels"],
                "activity": activity,
                "is_new": is_new,
                "case_type": case_type,
                "individuals": individuals
            })
        data = {
            "stats": {
                "total_customers": len(db.get("customers", [])),
                "total_individuals": total_individuals,
                "total_files": total_files,
                "new_today": new_today
            },
            "case_types": case_type_summary,
            "customers": customers_data
        }
        self._json_response(200, data)

    def _send_customer_detail(self, cust_id):
        db = load_json(CUSTOMERS_DB)
        leads_data = load_json(LEADS_FILE)
        leads_list = leads_data if isinstance(leads_data, list) else []
        customer = None
        for c in db.get("customers", []):
            if c.get("customerId") == cust_id or c.get("displayId") == cust_id:
                customer = c; break
        if not customer:
            self._json_response(404, {"error": "Not found"}); return
        # Issue #1: use displayId for folder
        folder_id = customer.get("displayId") or customer["customerId"]
        activity = scan_customer_activity(folder_id)
        individuals = customer.get("individuals", [])
        topic = ""
        if individuals:
            for ind in individuals:
                if ind.get("relationship") in ("self", ""):
                    topic = ind.get("topic", "")
                    break
            if not topic and individuals:
                topic = individuals[0].get("topic", "")
        lead_info = None
        for lead in leads_list:
            if lead.get("email") == customer["profile"].get("email"):
                lead_info = lead; break
        if lead_info and not lead_info.get("topic") and topic:
            lead_info["topic"] = topic
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
    print(f"[ADMIN] Dashboard v3 on port {PORT}")
    print(f"[ADMIN] BASE_DIR: {BASE_DIR}")
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        s.server_close()
