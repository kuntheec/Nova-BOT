#!/usr/bin/env python3
"""
Multi-Channel Webhook Server — for Nova BOT
Deploy to Render (free) + UptimeRobot
Channels: Facebook Messenger, LINE
"""

import json
import os
import datetime
import hashlib
import base64
import hmac
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── FB Config ──────────────────────────────────────────
VERIFY_TOKEN = "BENn1972"

# ── LINE Config ────────────────────────────────────────
LINE_CHANNEL_SECRET = "200c1bb0a53d1bb68bd1bf6fbebdb0a0"
LINE_CHANNEL_TOKEN = "Wx1PHI0XEXD2NFRhXvEIMWdw6J2BvR1BR808+2sS9fMu/421kAA13E+aDrbW+5+cr//M2jzGUR6c4h7eFVjTKdSk7zu0D3gQXEEph/GHtoPPQIPoQ0hsdB9g22WMMwRimAvwxWIJPsaxR75ESdWiGwdB04t89/1O/w1cDnyilFU="

# ── WhatsApp Config ────────────────────────────────────
WHATSAPP_VERIFY_TOKEN = "BENn1972"

# ── Storage ────────────────────────────────────────────
FB_MESSAGES_DIR = "fb_messages"
LINE_MESSAGES_DIR = "line_messages"
WHATSAPP_MESSAGES_DIR = "whatsapp_messages"
os.makedirs(FB_MESSAGES_DIR, exist_ok=True)
os.makedirs(LINE_MESSAGES_DIR, exist_ok=True)
os.makedirs(WHATSAPP_MESSAGES_DIR, exist_ok=True)

# ── Forward URL (ผ่าน Tailscale Funnel ไป local) ──────
FORWARD_URL_FB = "https://benpc.tailf7faa5.ts.net/messenger/save"
FORWARD_URL_LINE = "https://benpc.tailf7faa5.ts.net/linebot"
FORWARD_URL_WHATSAPP = "https://benpc.tailf7faa5.ts.net/whatsapp"


# ══════════════════════════════════════════════════════════
#  FACEBOOK MESSENGER
# ══════════════════════════════════════════════════════════

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Facebook ส่ง GET มาเพื่อ verify webhook"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print(f"[FB VERIFY] mode={mode}, token={token}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[FB VERIFY] SUCCESS!")
        return challenge, 200, {"Content-Type": "text/plain"}

    print("[FB VERIFY] FAILED")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_fb_webhook():
    """Facebook ส่ง POST มาเมื่อมีข้อความเข้า"""
    data = request.get_json(force=True)

    print(f"[FB MSG] Received Messenger webhook:")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:500])

    # บันทึกบน Render (Backup)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"msg_{now}_{abs(hash(str(data)))}.json"
    filepath = os.path.join(FB_MESSAGES_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[FB SAVED] {filepath}")

    # Forward ไปที่ local
    _forward_to_local(data, FORWARD_URL_FB)

    return jsonify({"status": "received"})


# ══════════════════════════════════════════════════════════
#  LINE
# ══════════════════════════════════════════════════════════

@app.route("/linebot", methods=["POST"])
def receive_line_webhook():
    """LINE Platform ส่ง POST มาเมื่อมีเหตุการณ์"""
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")

    # ตรวจสอบ signature
    expected = base64.b64encode(
        hmac.new(LINE_CHANNEL_SECRET.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()

    if not hmac.compare_digest(expected, signature):
        print("[LINE] Invalid signature!")
        return "Invalid signature", 400

    data = json.loads(body)
    print(f"[LINE] Received webhook: {len(data.get('events', []))} events")

    # บันทึกบน Render (Backup)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"line_{now}_{abs(hash(body))}.json"
    filepath = os.path.join(LINE_MESSAGES_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[LINE SAVED] {filepath}")

    # Forward ไป local (ส่ง body + headers เดิมทุกอย่าง)
    _forward_line_to_local(body, signature)

    return "OK"


def _forward_line_to_local(body, signature):
    """Forward LINE webhook payload ไป local server"""
    try:
        resp = requests.post(
            FORWARD_URL_LINE,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Line-Signature": signature,
            },
            timeout=10
        )
        if resp.status_code == 200:
            print(f"[LINE FORWARD] Success")
        else:
            print(f"[LINE FORWARD] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[LINE FORWARD] Error: {e}")


# ══════════════════════════════════════════════════════════
#  WHATSAPP CLOUD API
# ══════════════════════════════════════════════════════════

@app.route("/whatsapp", methods=["GET"])
def whatsapp_verify():
    """WhatsApp Cloud API ส่ง GET มาเพื่อ verify webhook"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print(f"[WA VERIFY] mode={mode}, token={token}")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        print("[WA VERIFY] SUCCESS!")
        return challenge, 200, {"Content-Type": "text/plain"}

    print("[WA VERIFY] FAILED")
    return "Forbidden", 403


@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """WhatsApp Cloud API ส่ง POST มาเมื่อมีข้อความเข้า"""
    data = request.get_json(force=True)

    print(f"[WA MSG] Received WhatsApp webhook:")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:500])

    # บันทึกบน Render (Backup)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"wa_{now}_{abs(hash(str(data)))}.json"
    filepath = os.path.join(WHATSAPP_MESSAGES_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[WA SAVED] {filepath}")

    # Forward ไปที่ local
    _forward_to_local(data, FORWARD_URL_WHATSAPP)

    return jsonify({"status": "received"})


# ══════════════════════════════════════════════════════════
#  SHARED
# ══════════════════════════════════════════════════════════

def _forward_to_local(data, url):
    """ส่งข้อมูล webhook ไปที่ local server (ผ่าน Tailscale Funnel)"""
    try:
        resp = requests.post(
            url,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.status_code == 200:
            print(f"[FORWARD] Success to {url}")
        else:
            print(f"[FORWARD] HTTP {resp.status_code} to {url}")
    except Exception as e:
        print(f"[FORWARD] Error to {url}: {e}")


@app.route("/privacy")
def privacy_policy():
    """Privacy Policy page"""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - Nova BOT</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }
        h2 { color: #16213e; margin-top: 30px; }
        p { margin: 10px 0; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Last updated:</strong> 2 June 2026</p>

    <h2>1. Introduction</h2>
    <p>Nova BOT ("we", "our", "us") operates the Messenger and WhatsApp bot service for The Global Manpower. This policy explains how we collect, use, and protect your personal information.</p>

    <h2>2. Information We Collect</h2>
    <p>When you interact with our bot, we may collect:</p>
    <ul>
        <li>Your name and profile information from Facebook/WhatsApp</li>
        <li>Messages and content you send to our Page</li>
        <li>Documents, images, and files you share (e.g., passport, visa documents)</li>
        <li>Your phone number (WhatsApp) or Facebook ID</li>
    </ul>

    <h2>3. How We Use Your Information</h2>
    <ul>
        <li>To respond to your inquiries and provide immigration consultation services</li>
        <li>To process and organize your documentation</li>
        <li>To communicate with you regarding your case</li>
        <li>To improve our services</li>
    </ul>

    <h2>4. Data Storage & Security</h2>
    <p>Your data is stored securely on our systems. We implement appropriate security measures to protect your personal information from unauthorized access, alteration, or disclosure.</p>

    <h2>5. Data Sharing</h2>
    <p>We do not sell your personal information. Your data is shared only with authorized personnel (immigration advisors) directly involved in your case.</p>

    <h2>6. Data Retention</h2>
    <p>We retain your data for the duration of your case and up to 12 months after case closure, unless otherwise required by law.</p>

    <h2>7. Your Rights</h2>
    <p>You have the right to request access, correction, or deletion of your personal data at any time by contacting us.</p>

    <h2>8. Contact</h2>
    <p>For privacy-related inquiries, contact us at: <strong>tgm.kuntheec@gmail.com</strong></p>

    <h2>9. Changes to This Policy</h2>
    <p>We may update this policy from time to time. Changes will be posted on this page.</p>
</body>
/html>"""


@app.route("/health")
def health_check():
    """Health check"""
    return jsonify({
        "status": "ok",
        "service": "Nova BOT Multi-Channel Webhook",
        "channels": ["facebook", "line", "whatsapp"]
    })


LANDING_HTML = base64.b64decode("PCFET0NUWVBFIGh0bWw+DQo8aHRtbCBsYW5nPSJ0aCI+DQo8aGVhZD4NCjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4NCjxtZXRhIG5hbWU9InZpZXdwb3J0IiBjb250ZW50PSJ3aWR0aD1kZXZpY2Utd2lkdGgsIGluaXRpYWwtc2NhbGU9MS4wIj4NCjx0aXRsZT5UaGUgR2xvYmFsIE1hbnBvd2VyIOKAlCBJbW1pZ3JhdGlvbiBTZXJ2aWNlczwvdGl0bGU+DQo8c3R5bGU+DQogICogeyBib3gtc2l6aW5nOiBib3JkZXItYm94OyBtYXJnaW46IDA7IHBhZGRpbmc6IDA7IH0NCiAgYm9keSB7DQogICAgZm9udC1mYW1pbHk6IC1hcHBsZS1zeXN0ZW0sIEJsaW5rTWFjU3lzdGVtRm9udCwgJ1NlZ29lIFVJJywgc2Fucy1zZXJpZjsNCiAgICBiYWNrZ3JvdW5kOiBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCAjMGYxNzJhIDAlLCAjMWUyOTNiIDEwMCUpOw0KICAgIG1pbi1oZWlnaHQ6IDEwMHZoOw0KICAgIGRpc3BsYXk6IGZsZXg7DQogICAgYWxpZ24taXRlbXM6IGNlbnRlcjsNCiAgICBqdXN0aWZ5LWNvbnRlbnQ6IGNlbnRlcjsNCiAgICBwYWRkaW5nOiAyMHB4Ow0KICB9DQogIC5jYXJkIHsNCiAgICBiYWNrZ3JvdW5kOiAjZmZmOw0KICAgIGJvcmRlci1yYWRpdXM6IDE2cHg7DQogICAgcGFkZGluZzogNDBweDsNCiAgICBtYXgtd2lkdGg6IDUyMHB4Ow0KICAgIHdpZHRoOiAxMDAlOw0KICAgIGJveC1zaGFkb3c6IDAgMjBweCA2MHB4IHJnYmEoMCwwLDAsMC4zKTsNCiAgfQ0KICAubG9nbyB7DQogICAgdGV4dC1hbGlnbjogY2VudGVyOw0KICAgIG1hcmdpbi1ib3R0b206IDI0cHg7DQogIH0NCiAgLmxvZ28gaDEgew0KICAgIGZvbnQtc2l6ZTogMjJweDsNCiAgICBjb2xvcjogIzFlMjkzYjsNCiAgICBtYXJnaW4tYm90dG9tOiA0cHg7DQogIH0NCiAgLmxvZ28gcCB7DQogICAgZm9udC1zaXplOiAxNHB4Ow0KICAgIGNvbG9yOiAjNjQ3NDhiOw0KICB9DQogIC5mb3JtLWdyb3VwIHsNCiAgICBtYXJnaW4tYm90dG9tOiAxOHB4Ow0KICB9DQogIGxhYmVsIHsNCiAgICBkaXNwbGF5OiBibG9jazsNCiAgICBmb250LXNpemU6IDEzcHg7DQogICAgZm9udC13ZWlnaHQ6IDYwMDsNCiAgICBjb2xvcjogIzMzNDE1NTsNCiAgICBtYXJnaW4tYm90dG9tOiA2cHg7DQogIH0NCiAgbGFiZWwgLm9wdGlvbmFsIHsNCiAgICBmb250LXdlaWdodDogNDAwOw0KICAgIGNvbG9yOiAjOTRhM2I4Ow0KICAgIGZvbnQtc2l6ZTogMTJweDsNCiAgfQ0KICBpbnB1dCwgc2VsZWN0IHsNCiAgICB3aWR0aDogMTAwJTsNCiAgICBwYWRkaW5nOiAxMnB4IDE0cHg7DQogICAgYm9yZGVyOiAxLjVweCBzb2xpZCAjZTJlOGYwOw0KICAgIGJvcmRlci1yYWRpdXM6IDEwcHg7DQogICAgZm9udC1zaXplOiAxNXB4Ow0KICAgIHRyYW5zaXRpb246IGJvcmRlci1jb2xvciAwLjJzOw0KICAgIG91dGxpbmU6IG5vbmU7DQogIH0NCiAgaW5wdXQ6Zm9jdXMsIHNlbGVjdDpmb2N1cyB7DQogICAgYm9yZGVyLWNvbG9yOiAjM2I4MmY2Ow0KICAgIGJveC1zaGFkb3c6IDAgMCAwIDNweCByZ2JhKDU5LDEzMCwyNDYsMC4xNSk7DQogIH0NCiAgLmJ0biB7DQogICAgd2lkdGg6IDEwMCU7DQogICAgcGFkZGluZzogMTRweDsNCiAgICBiYWNrZ3JvdW5kOiAjMjU2M2ViOw0KICAgIGNvbG9yOiAjZmZmOw0KICAgIGJvcmRlcjogbm9uZTsNCiAgICBib3JkZXItcmFkaXVzOiAxMHB4Ow0KICAgIGZvbnQtc2l6ZTogMTZweDsNCiAgICBmb250LXdlaWdodDogNjAwOw0KICAgIGN1cnNvcjogcG9pbnRlcjsNCiAgICB0cmFuc2l0aW9uOiBiYWNrZ3JvdW5kIDAuMnM7DQogICAgbWFyZ2luLXRvcDogOHB4Ow0KICB9DQogIC5idG46aG92ZXIgeyBiYWNrZ3JvdW5kOiAjMWQ0ZWQ4OyB9DQogIC5idG46ZGlzYWJsZWQgeyBvcGFjaXR5OiAwLjY7IGN1cnNvcjogbm90LWFsbG93ZWQ7IH0NCiAgLm5vdGUgew0KICAgIGZvbnQtc2l6ZTogMTJweDsNCiAgICBjb2xvcjogIzY0NzQ4YjsNCiAgICB0ZXh0LWFsaWduOiBjZW50ZXI7DQogICAgbWFyZ2luLXRvcDogMjBweDsNCiAgICBsaW5lLWhlaWdodDogMS41Ow0KICB9DQogIC5zdWNjZXNzIHsNCiAgICBkaXNwbGF5OiBub25lOw0KICAgIHRleHQtYWxpZ246IGNlbnRlcjsNCiAgICBwYWRkaW5nOiAzMHB4IDA7DQogIH0NCiAgLnN1Y2Nlc3MgLmNoZWNrIHsNCiAgICBmb250LXNpemU6IDQ4cHg7DQogICAgbWFyZ2luLWJvdHRvbTogMTJweDsNCiAgfQ0KICAuc3VjY2VzcyBoMiB7IGNvbG9yOiAjMTZhMzRhOyBtYXJnaW4tYm90dG9tOiA4cHg7IH0NCiAgLnN1Y2Nlc3MgcCB7IGNvbG9yOiAjNjQ3NDhiOyBmb250LXNpemU6IDE0cHg7IGxpbmUtaGVpZ2h0OiAxLjY7IH0NCiAgLmVycm9yLW1zZyB7DQogICAgZGlzcGxheTogbm9uZTsNCiAgICBjb2xvcjogI2RjMjYyNjsNCiAgICBmb250LXNpemU6IDEzcHg7DQogICAgbWFyZ2luLXRvcDogMTBweDsNCiAgICB0ZXh0LWFsaWduOiBjZW50ZXI7DQogIH0NCiAgLmNoYW5uZWxzLWhpbnQgew0KICAgIGJhY2tncm91bmQ6ICNmOGZhZmM7DQogICAgYm9yZGVyLXJhZGl1czogOHB4Ow0KICAgIHBhZGRpbmc6IDEycHg7DQogICAgZm9udC1zaXplOiAxMnB4Ow0KICAgIGNvbG9yOiAjNjQ3NDhiOw0KICAgIG1hcmdpbi1ib3R0b206IDE4cHg7DQogICAgbGluZS1oZWlnaHQ6IDEuNjsNCiAgfQ0KPC9zdHlsZT4NCjwvaGVhZD4NCjxib2R5Pg0KPGRpdiBjbGFzcz0iY2FyZCIgaWQ9ImZvcm1DYXJkIj4NCiAgPGRpdiBjbGFzcz0ibG9nbyI+DQogICAgPGgxPvCfjI8gVGhlIEdsb2JhbCBNYW5wb3dlcjwvaDE+DQogICAgPHA+SW1taWdyYXRpb24gQ29uc3VsdGF0aW9uIOKAlCDguKXguIfguJfguLDguYDguJrguLXguKLguJnguKPguLHguJrguITguLPguJvguKPguLbguIHguKnguLI8L3A+DQogIDwvZGl2Pg0KDQogIDxkaXYgY2xhc3M9ImNoYW5uZWxzLWhpbnQiPg0KICAgIOC4geC4o+C4uOC4k+C4suC4geC4o+C4reC4geC4guC5ieC4reC4oeC4ueC4peC4l+C4teC5iOC4leC4tOC4lOC4leC5iOC4reC5hOC4lOC5ieC4quC4sOC4lOC4p+C4gSDguYDguJ7guLfguYjguK3guYPguKvguYnguYDguKPguLLguKrguLLguKHguLLguKPguJbguJXguLTguJTguJXguYjguK3guYHguKXguLDguKrguYjguIfguYDguK3guIHguKrguLLguKPguIHguKXguLHguJrguJbguLbguIfguITguLjguJPguYTguJTguYnguJfguLjguIHguIrguYjguK3guIfguJfguLLguIc8YnI+PHN0cm9uZz7guJbguYnguLLguKXguIfguJfguLDguYDguJrguLXguKLguJnguYHguKXguYnguKcg4oCUIOC4geC4o+C4reC4geC4reC4teC5gOC4oeC4peC5gOC4lOC4tOC4oSDguKPguLDguJrguJrguIjguLDguK3guLHguJvguYDguJTguJXguILguYnguK3guKHguLnguKXguYPguKvguYnguK3guLHguJXguYLguJnguKHguLHguJXguLQ8L3N0cm9uZz4NCiAgPC9kaXY+DQoNCiAgPGZvcm0gaWQ9ImxlYWRGb3JtIj4NCiAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4NCiAgICAgIDxsYWJlbD7guIrguLfguYjguK0t4LiZ4Liy4Lih4Liq4LiB4Li44LilIDxzcGFuIGNsYXNzPSJvcHRpb25hbCI+Kjwvc3Bhbj48L2xhYmVsPg0KICAgICAgPGlucHV0IHR5cGU9InRleHQiIG5hbWU9Im5hbWUiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPSLguYDguIrguYjguJkg4Liq4Lih4LiK4Liy4LiiIOC5g+C4iOC4lOC4tSI+DQogICAgPC9kaXY+DQoNCiAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4NCiAgICAgIDxsYWJlbD7guYDguJrguK3guKPguYzguYLguJfguKPguKjguLHguJ7guJfguYwgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4qPC9zcGFuPjwvbGFiZWw+DQogICAgICA8aW5wdXQgdHlwZT0idGVsIiBuYW1lPSJwaG9uZSIgcmVxdWlyZWQgcGxhY2Vob2xkZXI9IuC5gOC4iuC5iOC4mSAwMjEyMzQ1Njc4Ij4NCiAgICA8L2Rpdj4NCg0KICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPg0KICAgICAgPGxhYmVsPuC4reC4teC5gOC4oeC4pSA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPio8L3NwYW4+PC9sYWJlbD4NCiAgICAgIDxpbnB1dCB0eXBlPSJlbWFpbCIgbmFtZT0iZW1haWwiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPSJ5b3VyQGVtYWlsLmNvbSI+DQogICAgPC9kaXY+DQoNCiAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4NCiAgICAgIDxsYWJlbD5MSU5FIElEIDxzcGFuIGNsYXNzPSJvcHRpb25hbCI+KG9wdGlvbmFsKTwvc3Bhbj48L2xhYmVsPg0KICAgICAgPGlucHV0IHR5cGU9InRleHQiIG5hbWU9ImxpbmVfaWQiIHBsYWNlaG9sZGVyPSJMSU5FIElEIOC4q+C4o+C4t+C4reC5gOC4muC4reC4o+C5jOC4l+C4teC5iOC4peC4h+C4l+C4sOC5gOC4muC4teC4ouC4mSBMSU5FIj4NCiAgICA8L2Rpdj4NCg0KICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPg0KICAgICAgPGxhYmVsPkZhY2Vib29rIE1lc3NlbmdlciA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPihvcHRpb25hbCk8L3NwYW4+PC9sYWJlbD4NCiAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBuYW1lPSJtZXNzZW5nZXJfaWQiIHBsYWNlaG9sZGVyPSLguIrguLfguYjguK3guJrguLHguI3guIrguLUgRmFjZWJvb2sg4Lir4Lij4Li34Lit4Lil4Li04LiH4LiB4LmM4LmC4Lib4Lij4LmE4Lif4Lil4LmMIj4NCiAgICA8L2Rpdj4NCg0KICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPg0KICAgICAgPGxhYmVsPldoYXRzQXBwIDxzcGFuIGNsYXNzPSJvcHRpb25hbCI+KG9wdGlvbmFsKTwvc3Bhbj48L2xhYmVsPg0KICAgICAgPGlucHV0IHR5cGU9InRlbCIgbmFtZT0id2hhdHNhcHAiIHBsYWNlaG9sZGVyPSLguYDguJrguK3guKPguYwgV2hhdHNBcHAgKOC4o+C4p+C4oeC4o+C4q+C4seC4quC4m+C4o+C4sOC5gOC4l+C4qCkiPg0KICAgIDwvZGl2Pg0KDQogICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+DQogICAgICA8bGFiZWw+4Lir4Lix4Lin4LiC4LmJ4Lit4LiX4Li14LmI4LiV4LmJ4Lit4LiH4LiB4Liy4Lij4Lib4Lij4Li24LiB4Lip4LiyPC9sYWJlbD4NCiAgICAgIDxzZWxlY3QgbmFtZT0idG9waWMiPg0KICAgICAgICA8b3B0aW9uIHZhbHVlPSJ2aXNhIj7guILguK0gVmlzYSAvIOC4leC5iOC4rSBWaXNhPC9vcHRpb24+DQogICAgICAgIDxvcHRpb24gdmFsdWU9InJlc2lkZW5jeSI+4LiW4Li04LmI4LiZ4LiX4Li14LmI4Lit4Lii4Li54LmIIChSZXNpZGVuY3kpPC9vcHRpb24+DQogICAgICAgIDxvcHRpb24gdmFsdWU9IndvcmsiPuC5g+C4muC4reC4meC4uOC4jeC4suC4leC4l+C4s+C4h+C4suC4mTwvb3B0aW9uPg0KICAgICAgICA8b3B0aW9uIHZhbHVlPSJmYW1pbHkiPkZhbWlseSAvIFBhcnRuZXIgVmlzYTwvb3B0aW9uPg0KICAgICAgICA8b3B0aW9uIHZhbHVlPSJvdGhlciI+4Lit4Li34LmI4LiZ4LmGPC9vcHRpb24+DQogICAgICA8L3NlbGVjdD4NCiAgICA8L2Rpdj4NCg0KICAgIDxidXR0b24gdHlwZT0ic3VibWl0IiBjbGFzcz0iYnRuIiBpZD0ic3VibWl0QnRuIj7guKrguYjguIfguILguYnguK3guKHguLnguKU8L2J1dHRvbj4NCiAgICA8ZGl2IGNsYXNzPSJlcnJvci1tc2ciIGlkPSJlcnJvck1zZyI+PC9kaXY+DQogIDwvZm9ybT4NCg0KICA8ZGl2IGNsYXNzPSJub3RlIj4NCiAgICDguILguYnguK3guKHguLnguKXguILguK3guIfguITguLjguJPguIjguLDguJbguLnguIHguYDguIHguYfguJrguYDguJvguYfguJnguITguKfguLLguKHguKXguLHguJrguYHguKXguLDguYPguIrguYnguKrguLPguKvguKPguLHguJrguIHguLLguKPguYPguKvguYnguITguLPguJvguKPguLbguIHguKnguLLguYDguJfguYjguLLguJnguLHguYnguJkNCiAgPC9kaXY+DQo8L2Rpdj4NCg0KPCEtLSBTdWNjZXNzIFNjcmVlbiAtLT4NCjxkaXYgY2xhc3M9ImNhcmQiIGlkPSJzdWNjZXNzQ2FyZCIgc3R5bGU9ImRpc3BsYXk6bm9uZTsiPg0KICA8ZGl2IGNsYXNzPSJzdWNjZXNzIj4NCiAgICA8ZGl2IGNsYXNzPSJjaGVjayI+4pyFPC9kaXY+DQogICAgPGgyPuC4quC5iOC4h+C4guC5ieC4reC4oeC4ueC4peC4quC4s+C5gOC4o+C5h+C4iCE8L2gyPg0KICAgIDxwPuC5gOC4o+C4suC4iOC4sOC4leC4tOC4lOC4leC5iOC4reC4geC4peC4seC4muC5guC4lOC4ouC5gOC4o+C5h+C4p+C4l+C4teC5iOC4quC4uOC4lOC4l+C4suC4h+C4iuC5iOC4reC4h+C4l+C4suC4h+C4l+C4teC5iOC4hOC4uOC4k+C5gOC4peC4t+C4reC4geC5hOC4p+C5iTxicj7guILguK3guJrguITguLjguJPguJfguLXguYjguYPguIrguYnguJrguKPguLTguIHguLLguKMgVGhlIEdsb2JhbCBNYW5wb3dlcjwvcD4NCiAgPC9kaXY+DQo8L2Rpdj4NCg0KPHNjcmlwdD4NCmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsZWFkRm9ybScpLmFkZEV2ZW50TGlzdGVuZXIoJ3N1Ym1pdCcsIGFzeW5jIGZ1bmN0aW9uKGUpIHsNCiAgZS5wcmV2ZW50RGVmYXVsdCgpOw0KICBjb25zdCBidG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3VibWl0QnRuJyk7DQogIGNvbnN0IGVyckVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Vycm9yTXNnJyk7DQogIGJ0bi5kaXNhYmxlZCA9IHRydWU7DQogIGJ0bi50ZXh0Q29udGVudCA9ICfguIHguLPguKXguLHguIfguKrguYjguIcuLi4nOw0KICBlcnJFbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOw0KDQogIGNvbnN0IGZvcm1EYXRhID0gbmV3IEZvcm1EYXRhKHRoaXMpOw0KICBjb25zdCBkYXRhID0gT2JqZWN0LmZyb21FbnRyaWVzKGZvcm1EYXRhLmVudHJpZXMoKSk7DQoNCiAgdHJ5IHsNCiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2xhbmRpbmcvc3VibWl0Jywgew0KICAgICAgbWV0aG9kOiAnUE9TVCcsDQogICAgICBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwNCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KGRhdGEpDQogICAgfSk7DQoNCiAgICBpZiAoIXJlcy5vaykgew0KICAgICAgY29uc3QgdGV4dCA9IGF3YWl0IHJlcy50ZXh0KCk7DQogICAgICB0aHJvdyBuZXcgRXJyb3IodGV4dCB8fCAn4Liq4LmI4LiH4LiC4LmJ4Lit4Lih4Li54Lil4LmE4Lih4LmI4Liq4Liz4LmA4Lij4LmH4LiIJyk7DQogICAgfQ0KDQogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Zvcm1DYXJkJykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsNCiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3VjY2Vzc0NhcmQnKS5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsNCiAgfSBjYXRjaCAoZXJyKSB7DQogICAgZXJyRWwudGV4dENvbnRlbnQgPSAn4LmA4LiB4Li04LiU4LiC4LmJ4Lit4Lic4Li04LiU4Lie4Lil4Liy4LiUOiAnICsgZXJyLm1lc3NhZ2UgKyAnIOC4geC4o+C4uOC4k+C4suC4peC4reC4h+C4reC4teC4geC4hOC4o+C4seC5ieC4hyc7DQogICAgZXJyRWwuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7DQogICAgYnRuLmRpc2FibGVkID0gZmFsc2U7DQogICAgYnRuLnRleHRDb250ZW50ID0gJ+C4quC5iOC4h+C4guC5ieC4reC4oeC4ueC4pSc7DQogIH0NCn0pOw0KPC9zY3JpcHQ+DQo8L2JvZHk+DQo8L2h0bWw+DQo=").decode("utf-8")


@app.route("/landing")
def landing_page():
    return LANDING_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/landing/submit", methods=["POST"])
def landing_submit():
    data = request.get_json(force=True)
    print(f"[LANDING] New registration: {data.get('name')} <{data.get('email')}>")
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"lead_{now}_{abs(hash(str(data)))}.json"
    leaddir = os.path.join(os.path.dirname(__file__), "landing_leads")
    os.makedirs(leaddir, exist_ok=True)
    filepath = os.path.join(leaddir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[LANDING SAVED] {filepath}")

    FORWARD_URL_LANDING = "https://benpc.tailf7faa5.ts.net/landing/save"
    try:
        resp = requests.post(FORWARD_URL_LANDING, json=data, headers={"Content-Type": "application/json"}, timeout=10)
        if resp.status_code == 200:
            print(f"[LANDING FORWARD] Success")
        else:
            print(f"[LANDING FORWARD] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[LANDING FORWARD] Error: {e}")

    return jsonify({"status": "received", "message": "Registration successful"})


if __name__ == "__main__":
    print("Nova BOT Multi-Channel Webhook ready!")
    print("  FB:  /webhook")
    print("  LINE: /linebot")
    print("  WA:   /whatsapp")
    app.run(host="0.0.0.0", port=10000, debug=False)
