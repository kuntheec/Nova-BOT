"""
consolidate_webhook_server.py
Production-ready unified webhook server for LINE, Messenger, WhatsApp.
All secrets and paths read from environment variables.
"""

import os
import json
import base64
import hashlib
import hmac
import time
import mimetypes
from datetime import datetime
from flask import Flask, request, send_file, abort
import requests

from dotenv import load_dotenv
load_dotenv()

# ========== ENVIRONMENT VARIABLES ==========
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN", "")
FB_VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ADMIN_TELEGRAM_CHAT_ID = os.getenv("ADMIN_TELEGRAM_CHAT_ID", "")
OPENCLAW_CLASSIFY_URL = os.getenv("OPENCLAW_CLASSIFY_URL", "http://localhost:5006/classify")

# Paths – derived from BASE_DIR
BASE_DIR = os.getenv("BASE_DIR", r"D:\ImmigrationCases")
CUSTOMERS_DB = os.getenv("CUSTOMERS_DB", os.path.join(BASE_DIR, "_Customers.json"))
LOG_FILE = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "_incoming.log"))

os.makedirs(BASE_DIR, exist_ok=True)
app = Flask(__name__)

# Startup validation
if not WHATSAPP_ACCESS_TOKEN:
    print("[WARNING] WHATSAPP_ACCESS_TOKEN is not set. WhatsApp media will not be downloaded.")
    print("         To enable, set the token in your .env file.")
else:
    print(f"[INFO] WhatsApp access token configured (length: {len(WHATSAPP_ACCESS_TOKEN)})")
print(f"[INFO] BASE_DIR: {BASE_DIR}")

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def log_incoming(entry):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[LOG] {entry.get('channel')} - {entry.get('type')} from {entry.get('sender_name', 'unknown')}")
    except Exception as e:
        print(f"Log error: {e}")

def load_customers_db(retries=3):
    for attempt in range(retries):
        try:
            with open(CUSTOMERS_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            if attempt == retries - 1:
                print(f"Failed to load customers DB: {e}")
                return {"customers_by_channel": {}, "customers": []}
            time.sleep(0.2)
    return {"customers_by_channel": {}, "customers": []}

def identify_customer(channel_type, sender_id):
    db = load_customers_db()
    key = f"{channel_type}:{sender_id}"
    customer_id = db.get("customers_by_channel", {}).get(key)
    if not customer_id:
        return None, None, None
    for cust in db.get("customers", []):
        if cust.get("customerId") == customer_id or cust.get("displayId") == customer_id:
            name = cust.get("profile", {}).get("name", customer_id)
            display = cust.get("displayId", customer_id)
            return customer_id, name, display
    return customer_id, customer_id, customer_id

def send_telegram(channel, name, display_id, msg_type, details):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    text = f"📩 {channel} — {name} ({display_id})\n{msg_type}\n{details}"
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

def notify_admin(channel, sender_id, sender_name, msg_type, details):
    if not ADMIN_TELEGRAM_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        return
    text = f"🔔 ADMIN ALERT\nChannel: {channel}\nFrom: {sender_name} ({sender_id})\nType: {msg_type}\n{details[:200]}"
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": ADMIN_TELEGRAM_CHAT_ID, "text": text}, timeout=5)
    except Exception as e:
        print(f"Admin notification error: {e}")

def save_text_message(content, customer_id, channel, sender_id, timestamp, is_known, display_id=None):
    folder_id = display_id if display_id else customer_id
    if is_known and folder_id:
        base_path = os.path.join(BASE_DIR, folder_id, "chats", channel)
    else:
        base_path = os.path.join(BASE_DIR, "_unknown", channel)
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H%M%S")
    target_dir = os.path.join(base_path, date_str)
    ensure_dir(target_dir)
    if is_known:
        filename = f"{time_str}_text.txt"
    else:
        safe_sender = "".join(c for c in sender_id if c.isalnum() or c in "_-").strip() or "unknown"
        filename = f"{safe_sender}_{time_str}_text.txt"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath

def save_binary_message(data, customer_id, channel, sender_id, timestamp, is_known, ext, original_filename=None, display_id=None):
    folder_id = display_id if display_id else customer_id
    if is_known and folder_id:
        base_path = os.path.join(BASE_DIR, folder_id, "chats", channel)
    else:
        base_path = os.path.join(BASE_DIR, "_unknown", channel)
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H%M%S")
    target_dir = os.path.join(base_path, date_str)
    ensure_dir(target_dir)
    if original_filename:
        safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._- ").strip()
        if not safe_name:
            safe_name = f"file_{time_str}{ext}"
        filename = f"{time_str}_{safe_name}"
    else:
        filename = f"{time_str}{ext}"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "wb") as f:
        f.write(data)
    return filepath

# Document classification (basic keyword)
DOCUMENT_KEYWORDS = {
    "passport": "Passport",
    "id_card": "ID_Card",
    "birth_cert": "Birth_Certificate",
    "marriage": "Marriage_Certificate",
    "divorce": "Divorce_Certificate",
    "police": "Police_Clearance",
    "medical": "Medical_Certificate",
    "education": "Education_Certificate",
    "work_permit": "Work_Permit",
    "visa": "Visa",
    "photo": "Photo"
}

def detect_document_type(filename):
    if not filename:
        return None
    fname_lower = filename.lower()
    for key, doc_type in DOCUMENT_KEYWORDS.items():
        if key in fname_lower:
            return doc_type
    return None

def notify_openclaw(filepath, customer_id, display_id, original_filename):
    if not OPENCLAW_CLASSIFY_URL:
        return
    try:
        payload = {
            "filepath": filepath,
            "customer_id": customer_id,
            "display_id": display_id,
            "original_filename": original_filename or ""
        }
        requests.post(OPENCLAW_CLASSIFY_URL, json=payload, timeout=2)
    except Exception as e:
        print(f"OpenClaw notification failed: {e}")

PENDING_OCR_DIR = os.path.join(BASE_DIR, "_pending_ocr")
os.makedirs(PENDING_OCR_DIR, exist_ok=True)

def enqueue_for_ocr(filepath, customer_id, display_id, original_filename):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base_name = os.path.basename(filepath)
        dest_filename = f"{customer_id}_{display_id}_{timestamp}_{base_name}"
        dest_path = os.path.join(PENDING_OCR_DIR, dest_filename)
        try:
            os.link(filepath, dest_path)
        except (OSError, NotImplementedError):
            import shutil
            shutil.copy2(filepath, dest_path)
        meta = {
            "original_filepath": filepath,
            "customer_id": customer_id,
            "display_id": display_id,
            "original_filename": original_filename,
            "timestamp": datetime.now().isoformat(),
            "pending_file": dest_path
        }
        with open(dest_path + ".meta", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print(f"[ENQUEUE] File queued for OCR: {dest_path}")
    except Exception as e:
        print(f"[ENQUEUE ERROR] {e}")

def save_binary_message_with_type(data, customer_id, channel, sender_id, timestamp, is_known, ext, original_filename=None, display_id=None):
    doc_type = detect_document_type(original_filename or "")
    folder_id = display_id if display_id else customer_id
    if doc_type and is_known and folder_id:
        base_path = os.path.join(BASE_DIR, folder_id, "documents", doc_type)
        date_str = timestamp.strftime("%Y-%m-%d")
        target_dir = os.path.join(base_path, date_str)
        ensure_dir(target_dir)
        time_str = timestamp.strftime("%H%M%S")
        new_filename = f"{doc_type}_{time_str}{ext}"
        filepath = os.path.join(target_dir, new_filename)
        with open(filepath, "wb") as f:
            f.write(data)
        if is_known and folder_id:
            notify_openclaw(filepath, customer_id, folder_id, original_filename)
        return filepath
    else:
        filepath = save_binary_message(data, customer_id, channel, sender_id, timestamp, is_known, ext, original_filename, display_id)
        if is_known and folder_id:
            enqueue_for_ocr(filepath, customer_id, folder_id, original_filename)
        return filepath

# ========== LINE HANDLER ==========
def get_line_user_name(user_id):
    try:
        r = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}",
                         headers={"Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"}, timeout=10)
        if r.status_code == 200:
            return r.json().get("displayName", user_id)
    except:
        pass
    return user_id

def reply_line(reply_token, text):
    try:
        requests.post("https://api.line.me/v2/bot/message/reply",
                      headers={"Authorization": f"Bearer {LINE_CHANNEL_TOKEN}",
                               "Content-Type": "application/json"},
                      json={"replyToken": reply_token,
                            "messages": [{"type": "text", "text": text}]}, timeout=10)
    except Exception as e:
        print(f"LINE reply error: {e}")

def download_line_media(message_id):
    for ep in ["https://api-data.line.me", "https://api.line.me"]:
        try:
            r = requests.get(f"{ep}/v2/bot/message/{message_id}/content",
                             headers={"Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"}, timeout=30)
            if r.status_code == 200 and r.content:
                return r.content
        except:
            continue
    return None

@app.route("/linebot", methods=["POST"])
def line_webhook():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    expected = base64.b64encode(hmac.new(LINE_CHANNEL_SECRET.encode(), body.encode(), hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(expected, signature):
        return "Invalid signature", 400
    try:
        data = json.loads(body)
    except:
        return "Bad JSON", 400
    for event in data.get("events", []):
        try:
            msg = event.get("message", {})
            msg_type = msg.get("type")
            msg_id = msg.get("id", "")
            reply_token = event.get("replyToken", "")
            user_id = event.get("source", {}).get("userId", "unknown")
            user_name = get_line_user_name(user_id)
            timestamp = datetime.now()
            cust_id, cust_name, display_id = identify_customer("line", user_id)
            is_known = cust_id is not None
            sender_display = cust_name if is_known else user_name
            entry = {
                "time": timestamp.isoformat(),
                "channel": "line",
                "sender_id": user_id,
                "sender_name": sender_display,
                "type": msg_type,
                "customer_id": cust_id,
                "display_id": display_id
            }
            if msg_type == "text":
                text = msg.get("text", "")
                filepath = save_text_message(text, cust_id, "line", user_id, timestamp, is_known, display_id)
                entry["text"] = text
                entry["saved_to"] = filepath
                reply_line(reply_token, f"You said: {text}")
                if is_known:
                    send_telegram("LINE", sender_display, display_id, "text", text[:100])
                notify_admin("LINE", user_id, sender_display, "text", text[:100])
            elif msg_type in ("image", "file"):
                raw = download_line_media(msg_id)
                if raw:
                    if msg_type == "image":
                        ext = ".jpg"
                        orig = None
                    else:
                        ext = os.path.splitext(msg.get("fileName", ""))[1] or ".bin"
                        orig = msg.get("fileName")
                    filepath = save_binary_message_with_type(raw, cust_id, "line", user_id, timestamp, is_known, ext, orig, display_id)
                    entry["saved_to"] = filepath
                    entry["size"] = len(raw)
                    reply_line(reply_token, f"Got your {msg_type}, {sender_display}!")
                    if is_known:
                        send_telegram("LINE", sender_display, display_id, msg_type, f"Saved: {os.path.basename(filepath)}")
                    notify_admin("LINE", user_id, sender_display, msg_type, f"File: {orig or 'image'} -> {os.path.basename(filepath)}")
                else:
                    entry["error"] = "download failed"
                    reply_line(reply_token, "Couldn't download that.")
                    notify_admin("LINE", user_id, sender_display, msg_type, "Download failed")
            else:
                entry["detail"] = f"unsupported type: {msg_type}"
                reply_line(reply_token, f"Got your {msg_type}!")
                notify_admin("LINE", user_id, sender_display, msg_type, "Unsupported type")
            log_incoming(entry)
        except Exception as e:
            log_incoming({"channel": "line", "error": str(e), "time": datetime.now().isoformat()})
    return "OK"

# ========== MESSENGER COMMON PROCESSING ==========
def download_messenger_media(attachment_url):
    if not FB_PAGE_ACCESS_TOKEN:
        print("Messenger download skipped: no FB_PAGE_ACCESS_TOKEN")
        return None
    try:
        download_url = f"{attachment_url}?access_token={FB_PAGE_ACCESS_TOKEN}"
        resp = requests.get(download_url, timeout=30)
        if resp.status_code == 200 and resp.content:
            return resp.content
        else:
            print(f"Messenger download failed: {resp.status_code}")
    except Exception as e:
        print(f"Messenger download error: {e}")
    return None

def process_messenger_message(sender_id, message, timestamp, is_forwarded=False):
    cust_id, cust_name, display_id = identify_customer("messenger", sender_id)
    is_known = cust_id is not None
    sender_display = cust_name if is_known else sender_id
    entry = {
        "time": timestamp.isoformat(),
        "channel": "messenger",
        "sender_id": sender_id,
        "sender_name": sender_display,
        "type": None,
        "customer_id": cust_id,
        "display_id": display_id,
        "forwarded": is_forwarded
    }
    if "text" in message:
        text = message["text"]
        filepath = save_text_message(text, cust_id, "messenger", sender_id, timestamp, is_known, display_id)
        entry["type"] = "text"
        entry["text"] = text
        entry["saved_to"] = filepath
        if is_known:
            send_telegram("Messenger", sender_display, display_id, "text", text[:100])
        notify_admin("Messenger", sender_id, sender_display, "text", text[:100])
    elif "attachments" in message:
        entry["type"] = "attachment"
        for att in message["attachments"]:
            att_type = att.get("type")
            payload = att.get("payload", {})
            url = payload.get("url")
            if url and att_type in ("image", "video", "audio", "file"):
                raw = download_messenger_media(url)
                if raw:
                    if att_type == "image":
                        ext = ".jpg"
                    elif att_type == "video":
                        ext = ".mp4"
                    else:
                        ext = ".bin"
                    filepath = save_binary_message_with_type(
                        raw, cust_id, "messenger", sender_id, timestamp, is_known, ext,
                        original_filename=f"{att_type}_from_messenger", display_id=display_id
                    )
                    entry.setdefault("saved_attachments", []).append(filepath)
                    entry.setdefault("sizes", []).append(len(raw))
                    if is_known:
                        send_telegram("Messenger", sender_display, display_id, att_type, f"Saved: {os.path.basename(filepath)}")
                    notify_admin("Messenger", sender_id, sender_display, att_type, f"File: {os.path.basename(filepath)}")
                else:
                    entry["error"] = f"Failed to download {att_type}"
                    notify_admin("Messenger", sender_id, sender_display, att_type, "Download failed")
            else:
                entry.setdefault("attachment_urls", []).append(f"{att_type}:{url or 'no_url'}")
        if entry.get("attachment_urls"):
            entry["attachment_urls"] = ", ".join(entry["attachment_urls"])
            notify_admin("Messenger", sender_id, sender_display, "attachment_url", entry["attachment_urls"][:200])
    else:
        entry["type"] = "unknown"
        entry["detail"] = "Non-text message without attachments"
        notify_admin("Messenger", sender_id, sender_display, "unknown", "No text/attachments")
    return entry

@app.route("/webhook", methods=["GET"])
def fb_verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == FB_VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def fb_webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        if data.get("object") != "page":
            return "Not a page event", 400
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                if not sender_id:
                    continue
                message = messaging.get("message", {})
                if not message:
                    continue
                timestamp = datetime.now()
                entry_log = process_messenger_message(sender_id, message, timestamp, is_forwarded=False)
                log_incoming(entry_log)
        return "OK", 200
    except Exception as e:
        log_incoming({"channel": "messenger", "error": str(e), "time": datetime.now().isoformat()})
        return "Error", 500

@app.route("/messenger/save", methods=["POST"])
def fb_save():
    try:
        data = request.get_json(force=True, silent=True) or {}
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                if not sender_id:
                    continue
                message = messaging.get("message", {})
                if not message:
                    continue
                timestamp = datetime.now()
                entry_log = process_messenger_message(sender_id, message, timestamp, is_forwarded=True)
                log_incoming(entry_log)
        return "OK", 200
    except Exception as e:
        log_incoming({"channel": "messenger", "error": str(e), "time": datetime.now().isoformat()})
        return "Error", 500

# ========== WHATSAPP HANDLER ==========
_wa_token_warned = False

def download_whatsapp_media(media_id):
    global _wa_token_warned
    if not WHATSAPP_ACCESS_TOKEN:
        if not _wa_token_warned:
            print("[WARNING] WHATSAPP_ACCESS_TOKEN is not set. WhatsApp media downloads will be skipped.")
            _wa_token_warned = True
        return None
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    try:
        resp = requests.get(f"https://graph.facebook.com/v21.0/{media_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        media_url = resp.json().get("url")
        if not media_url:
            return None
        dl = requests.get(media_url, headers=headers, timeout=30)
        if dl.status_code == 200:
            return dl.content
    except Exception as e:
        print(f"WhatsApp download error: {e}")
    return None

@app.route("/whatsapp", methods=["GET"])
def wa_verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification failed", 403

@app.route("/whatsapp", methods=["POST"])
def wa_webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        if data.get("object") != "whatsapp_business_account":
            return "Invalid object", 400
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    sender = msg.get("from")
                    if not sender:
                        continue
                    timestamp_epoch = int(msg.get("timestamp", time.time()))
                    dt = datetime.fromtimestamp(timestamp_epoch)
                    msg_type = msg.get("type", "unknown")
                    cust_id, cust_name, display_id = identify_customer("whatsapp", sender)
                    is_known = cust_id is not None
                    sender_display = cust_name if is_known else sender
                    entry = {
                        "time": dt.isoformat(),
                        "channel": "whatsapp",
                        "sender_id": sender,
                        "sender_name": sender_display,
                        "type": msg_type,
                        "customer_id": cust_id,
                        "display_id": display_id
                    }
                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "")
                        filepath = save_text_message(text, cust_id, "whatsapp", sender, dt, is_known, display_id)
                        entry["text"] = text
                        entry["saved_to"] = filepath
                        if is_known:
                            send_telegram("WhatsApp", sender_display, display_id, "text", text[:100])
                        notify_admin("WhatsApp", sender, sender_display, "text", text[:100])
                    elif msg_type in ("image", "document", "audio", "video"):
                        media_id = msg.get(msg_type, {}).get("id")
                        if media_id:
                            if WHATSAPP_ACCESS_TOKEN:
                                raw = download_whatsapp_media(media_id)
                                if raw:
                                    if msg_type == "image":
                                        ext = ".jpg"
                                        orig = None
                                    elif msg_type == "document":
                                        orig = msg.get(msg_type, {}).get("filename", "")
                                        ext = os.path.splitext(orig)[1] or ".bin"
                                    else:
                                        ext = ".bin"
                                        orig = None
                                    filepath = save_binary_message_with_type(raw, cust_id, "whatsapp", sender, dt, is_known, ext, orig, display_id)
                                    entry["saved_to"] = filepath
                                    entry["size"] = len(raw)
                                    if is_known:
                                        send_telegram("WhatsApp", sender_display, display_id, msg_type, f"Media: {os.path.basename(filepath)}")
                                    notify_admin("WhatsApp", sender, sender_display, msg_type, f"File: {os.path.basename(filepath)}")
                                else:
                                    entry["error"] = "Media download failed"
                                    notify_admin("WhatsApp", sender, sender_display, msg_type, "Download failed")
                            else:
                                entry["error"] = "WHATSAPP_ACCESS_TOKEN not set"
                                entry["media_id"] = media_id
                                notify_admin("WhatsApp", sender, sender_display, msg_type, "No access token")
                        else:
                            entry["error"] = "No media ID"
                            notify_admin("WhatsApp", sender, sender_display, msg_type, "No media ID")
                    else:
                        entry["detail"] = f"Unsupported type: {msg_type}"
                        notify_admin("WhatsApp", sender, sender_display, msg_type, "Unsupported type")
                    log_incoming(entry)
        return "OK", 200
    except Exception as e:
        log_incoming({"channel": "whatsapp", "error": str(e), "time": datetime.now().isoformat()})
        return "Error", 500

# ========== FILE BROWSING AND VIEWING ==========
def is_safe_path(base, path):
    abs_base = os.path.abspath(base)
    abs_path = os.path.abspath(os.path.join(abs_base, path))
    return abs_path.startswith(abs_base)

@app.route("/browse/<customer_id>")
def browse_customer(customer_id):
    customer_folder = os.path.join(BASE_DIR, customer_id)
    if not os.path.isdir(customer_folder):
        return f"Customer {customer_id} not found.", 404
    file_list = []
    for root, dirs, files in os.walk(customer_folder):
        rel_root = os.path.relpath(root, customer_folder)
        for f in files:
            if f.endswith('.meta') or f.endswith('.ocr.txt'):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.join(rel_root, f) if rel_root != '.' else f
            file_list.append({
                "name": f,
                "path": rel_path,
                "size": os.path.getsize(full_path),
                "modified": datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat()
            })
    html = f"""
    <html>
    <head><title>Customer {customer_id} Files</title></head>
    <body>
    <h1>Customer: {customer_id}</h1>
    <table border="1" cellpadding="5">
    <tr><th>File</th><th>Size (bytes)</th><th>Modified</th><th>Action</th></tr>
    """
    for item in sorted(file_list, key=lambda x: x['modified'], reverse=True):
        html += f"""
        <tr>
            <td>{item['name']}</td>
            <td>{item['size']}</td>
            <td>{item['modified']}</td>
            <td><a href="/file/{customer_id}/{item['path']}" target="_blank">View</a></td>
        </tr>
        """
    html += "</table></body></html>"
    return html

@app.route("/file/<customer_id>/<path:filepath>")
def serve_customer_file(customer_id, filepath):
    base_customer = os.path.join(BASE_DIR, customer_id)
    if not is_safe_path(BASE_DIR, os.path.join(customer_id, filepath)):
        abort(403)
    full_path = os.path.join(base_customer, filepath)
    if not os.path.exists(full_path):
        abort(404)
    mime_type, _ = mimetypes.guess_type(full_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'
    as_attachment = not (mime_type.startswith('image/') or mime_type == 'application/pdf')
    return send_file(full_path, mimetype=mime_type, as_attachment=as_attachment)

# ========== HEALTH & LOGS ==========
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@app.route("/msgs", methods=["GET"])
def list_messages():
    if not os.path.exists(LOG_FILE):
        return "<html><body><h2>No messages yet</h2></body></html>"
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        html = "<html><head><title>Incoming Messages</title></head><body>"
        html += "<h2>Recent Messages (last 50)</h2><pre>"
        for line in lines[-50:]:
            try:
                d = json.loads(line)
                html += json.dumps(d, indent=2, ensure_ascii=False) + "\n---\n"
            except:
                html += line + "\n---\n"
        html += "</pre></body></html>"
        return html
    except Exception as e:
        return f"<html><body>Error: {e}</body></html>"

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
