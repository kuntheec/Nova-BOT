"""
consolidate_webhook_server.py
Production-ready unified webhook server for LINE, Messenger, WhatsApp.
All secrets read from environment variables.
"""

import os
import json
import base64
import hashlib
import hmac
import time
from datetime import datetime
from flask import Flask, request
import requests

from dotenv import load_dotenv
load_dotenv()  # loads variables from .env

# ========== ENVIRONMENT VARIABLES (set these on Render/local .env) ==========
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN", "")
FB_VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CUSTOMERS_DB = os.getenv("CUSTOMERS_DB", r"D:\ImmigrationCases\_Customers.json")
BASE_DIR = os.getenv("BASE_DIR", r"D:\ImmigrationCases")
LOG_FILE = os.getenv("LOG_FILE", r"D:\ImmigrationCases\_incoming.log")

# ========== INIT ==========
os.makedirs(BASE_DIR, exist_ok=True)
app = Flask(__name__)

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

def load_customers_db():
    try:
        with open(CUSTOMERS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
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

def save_text_message(content, customer_id, channel, sender_id, timestamp, is_known):
    if is_known and customer_id:
        base_path = os.path.join(BASE_DIR, customer_id, "chats", channel)
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

def save_binary_message(data, customer_id, channel, sender_id, timestamp, is_known, ext, original_filename=None):
    if is_known and customer_id:
        base_path = os.path.join(BASE_DIR, customer_id, "chats", channel)
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

# ========== LINE ==========
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
                filepath = save_text_message(text, cust_id, "line", user_id, timestamp, is_known)
                entry["text"] = text
                entry["saved_to"] = filepath
                reply_line(reply_token, f"You said: {text}")
                if is_known:
                    send_telegram("LINE", sender_display, display_id, "text", text[:100])
            elif msg_type in ("image", "file"):
                raw = download_line_media(msg_id)
                if raw:
                    if msg_type == "image":
                        ext = ".jpg"
                        orig = None
                    else:
                        ext = os.path.splitext(msg.get("fileName", ""))[1] or ".bin"
                        orig = msg.get("fileName")
                    filepath = save_binary_message(raw, cust_id, "line", user_id, timestamp, is_known, ext, orig)
                    entry["saved_to"] = filepath
                    entry["size"] = len(raw)
                    reply_line(reply_token, f"Got your {msg_type}, {sender_display}!")
                    if is_known:
                        send_telegram("LINE", sender_display, display_id, msg_type, f"Saved: {os.path.basename(filepath)}")
                else:
                    entry["error"] = "download failed"
                    reply_line(reply_token, "Couldn't download that.")
            else:
                entry["detail"] = f"unsupported type: {msg_type}"
                reply_line(reply_token, f"Got your {msg_type}!")
            log_incoming(entry)
        except Exception as e:
            log_incoming({"channel": "line", "error": str(e), "time": datetime.now().isoformat()})
    return "OK"

# ========== FACEBOOK MESSENGER ==========
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
                timestamp = datetime.now()
                message = messaging.get("message", {})
                if not message:
                    continue
                msg_type = "text" if "text" in message else "attachment" if "attachments" else "unknown"
                cust_id, cust_name, display_id = identify_customer("messenger", sender_id)
                is_known = cust_id is not None
                sender_display = cust_name if is_known else sender_id
                entry = {
                    "time": timestamp.isoformat(),
                    "channel": "messenger",
                    "sender_id": sender_id,
                    "sender_name": sender_display,
                    "type": msg_type,
                    "customer_id": cust_id,
                    "display_id": display_id
                }
                if "text" in message:
                    text = message["text"]
                    filepath = save_text_message(text, cust_id, "messenger", sender_id, timestamp, is_known)
                    entry["text"] = text
                    entry["saved_to"] = filepath
                    if is_known:
                        send_telegram("Messenger", sender_display, display_id, "text", text[:100])
                elif "attachments" in message:
                    attachment_urls = []
                    for att in message["attachments"]:
                        att_type = att.get("type")
                        url = att.get("payload", {}).get("url", "no_url")
                        attachment_urls.append(f"{att_type}:{url}")
                        # Per spec, just log the URL – no download.
                    entry["attachment_urls"] = ", ".join(attachment_urls)
                    if is_known:
                        send_telegram("Messenger", sender_display, display_id, "attachment", entry["attachment_urls"][:200])
                else:
                    entry["detail"] = "Non-text message without attachments"
                log_incoming(entry)
        return "OK", 200
    except Exception as e:
        log_incoming({"channel": "messenger", "error": str(e), "time": datetime.now().isoformat()})
        return "Error", 500

# ========== WHATSAPP ==========
def download_whatsapp_media(media_id):
    if not WHATSAPP_ACCESS_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    try:
        # get media URL
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
                        filepath = save_text_message(text, cust_id, "whatsapp", sender, dt, is_known)
                        entry["text"] = text
                        entry["saved_to"] = filepath
                        if is_known:
                            send_telegram("WhatsApp", sender_display, display_id, "text", text[:100])
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
                                    filepath = save_binary_message(raw, cust_id, "whatsapp", sender, dt, is_known, ext, orig)
                                    entry["saved_to"] = filepath
                                    entry["size"] = len(raw)
                                    if is_known:
                                        send_telegram("WhatsApp", sender_display, display_id, msg_type, f"Media: {os.path.basename(filepath)}")
                                else:
                                    entry["error"] = "Media download failed"
                            else:
                                entry["error"] = "WHATSAPP_ACCESS_TOKEN not set"
                                entry["media_id"] = media_id
                        else:
                            entry["error"] = "No media ID"
                    else:
                        entry["detail"] = f"Unsupported type: {msg_type}"
                    log_incoming(entry)
        return "OK", 200
    except Exception as e:
        log_incoming({"channel": "whatsapp", "error": str(e), "time": datetime.now().isoformat()})
        return "Error", 500

# ========== HEALTH & LOG VIEWER ==========
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
