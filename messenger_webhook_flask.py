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
VERIFY_TOKEN = "nova123"

# ── LINE Config ────────────────────────────────────────
LINE_CHANNEL_SECRET = "200c1bb0a53d1bb68bd1bf6fbebdb0a0"
LINE_CHANNEL_TOKEN = "Wx1PHI0XEXD2NFRhXvEIMWdw6J2BvR1BR808+2sS9fMu/421kAA13E+aDrbW+5+cr//M2jzGUR6c4h7eFVjTKdSk7zu0D3gQXEEph/GHtoPPQIPoQ0hsdB9g22WMMwRimAvwxWIJPsaxR75ESdWiGwdB04t89/1O/w1cDnyilFU="

# ── WhatsApp Config ────────────────────────────────────
WHATSAPP_VERIFY_TOKEN = "nova123"

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


LANDING_HTML = base64.b64decode("PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9InRoIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+VGhlIEdsb2JhbCBNYW5wb3dlciDigJQgSW1taWdyYXRpb24gU2VydmljZXM8L3RpdGxlPgo8c3R5bGU+CiAgKiB7IGJveC1zaXppbmc6IGJvcmRlci1ib3g7IG1hcmdpbjogMDsgcGFkZGluZzogMDsgfQogIGJvZHkgewogICAgZm9udC1mYW1pbHk6IC1hcHBsZS1zeXN0ZW0sIEJsaW5rTWFjU3lzdGVtRm9udCwgJ1NlZ29lIFVJJywgc2Fucy1zZXJpZjsKICAgIGJhY2tncm91bmQ6IGxpbmVhci1ncmFkaWVudCgxMzVkZWcsICMwZjE3MmEgMCUsICMxZTI5M2IgMTAwJSk7CiAgICBtaW4taGVpZ2h0OiAxMDB2aDsKICAgIGRpc3BsYXk6IGZsZXg7CiAgICBhbGlnbi1pdGVtczogY2VudGVyOwogICAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7CiAgICBwYWRkaW5nOiAyMHB4OwogIH0KICAuY2FyZCB7CiAgICBiYWNrZ3JvdW5kOiAjZmZmOwogICAgYm9yZGVyLXJhZGl1czogMTZweDsKICAgIHBhZGRpbmc6IDQwcHg7CiAgICBtYXgtd2lkdGg6IDUyMHB4OwogICAgd2lkdGg6IDEwMCU7CiAgICBib3gtc2hhZG93OiAwIDIwcHggNjBweCByZ2JhKDAsMCwwLDAuMyk7CiAgfQogIC5sb2dvIHsKICAgIHRleHQtYWxpZ246IGNlbnRlcjsKICAgIG1hcmdpbi1ib3R0b206IDI0cHg7CiAgfQogIC5sb2dvIGgxIHsKICAgIGZvbnQtc2l6ZTogMjJweDsKICAgIGNvbG9yOiAjMWUyOTNiOwogICAgbWFyZ2luLWJvdHRvbTogNHB4OwogIH0KICAubG9nbyBwIHsKICAgIGZvbnQtc2l6ZTogMTRweDsKICAgIGNvbG9yOiAjNjQ3NDhiOwogIH0KICAuZm9ybS1ncm91cCB7CiAgICBtYXJnaW4tYm90dG9tOiAxOHB4OwogIH0KICBsYWJlbCB7CiAgICBkaXNwbGF5OiBibG9jazsKICAgIGZvbnQtc2l6ZTogMTNweDsKICAgIGZvbnQtd2VpZ2h0OiA2MDA7CiAgICBjb2xvcjogIzMzNDE1NTsKICAgIG1hcmdpbi1ib3R0b206IDZweDsKICB9CiAgbGFiZWwgLm9wdGlvbmFsIHsKICAgIGZvbnQtd2VpZ2h0OiA0MDA7CiAgICBjb2xvcjogIzk0YTNiODsKICAgIGZvbnQtc2l6ZTogMTJweDsKICB9CiAgaW5wdXQsIHNlbGVjdCB7CiAgICB3aWR0aDogMTAwJTsKICAgIHBhZGRpbmc6IDEycHggMTRweDsKICAgIGJvcmRlcjogMS41cHggc29saWQgI2UyZThmMDsKICAgIGJvcmRlci1yYWRpdXM6IDEwcHg7CiAgICBmb250LXNpemU6IDE1cHg7CiAgICB0cmFuc2l0aW9uOiBib3JkZXItY29sb3IgMC4yczsKICAgIG91dGxpbmU6IG5vbmU7CiAgfQogIGlucHV0OmZvY3VzLCBzZWxlY3Q6Zm9jdXMgewogICAgYm9yZGVyLWNvbG9yOiAjM2I4MmY2OwogICAgYm94LXNoYWRvdzogMCAwIDAgM3B4IHJnYmEoNTksMTMwLDI0NiwwLjE1KTsKICB9CiAgLmJ0biB7CiAgICB3aWR0aDogMTAwJTsKICAgIHBhZGRpbmc6IDE0cHg7CiAgICBiYWNrZ3JvdW5kOiAjMjU2M2ViOwogICAgY29sb3I6ICNmZmY7CiAgICBib3JkZXI6IG5vbmU7CiAgICBib3JkZXItcmFkaXVzOiAxMHB4OwogICAgZm9udC1zaXplOiAxNnB4OwogICAgZm9udC13ZWlnaHQ6IDYwMDsKICAgIGN1cnNvcjogcG9pbnRlcjsKICAgIHRyYW5zaXRpb246IGJhY2tncm91bmQgMC4yczsKICAgIG1hcmdpbi10b3A6IDhweDsKICB9CiAgLmJ0bjpob3ZlciB7IGJhY2tncm91bmQ6ICMxZDRlZDg7IH0KICAuYnRuOmRpc2FibGVkIHsgb3BhY2l0eTogMC42OyBjdXJzb3I6IG5vdC1hbGxvd2VkOyB9CiAgLm5vdGUgewogICAgZm9udC1zaXplOiAxMnB4OwogICAgY29sb3I6ICM2NDc0OGI7CiAgICB0ZXh0LWFsaWduOiBjZW50ZXI7CiAgICBtYXJnaW4tdG9wOiAyMHB4OwogICAgbGluZS1oZWlnaHQ6IDEuNTsKICB9CiAgLnN1Y2Nlc3MgewogICAgZGlzcGxheTogbm9uZTsKICAgIHRleHQtYWxpZ246IGNlbnRlcjsKICAgIHBhZGRpbmc6IDMwcHggMDsKICB9CiAgLnN1Y2Nlc3MgLmNoZWNrIHsKICAgIGZvbnQtc2l6ZTogNDhweDsKICAgIG1hcmdpbi1ib3R0b206IDEycHg7CiAgfQogIC5zdWNjZXNzIGgyIHsgY29sb3I6ICMxNmEzNGE7IG1hcmdpbi1ib3R0b206IDhweDsgfQogIC5zdWNjZXNzIHAgeyBjb2xvcjogIzY0NzQ4YjsgZm9udC1zaXplOiAxNHB4OyBsaW5lLWhlaWdodDogMS42OyB9CiAgLmVycm9yLW1zZyB7CiAgICBkaXNwbGF5OiBub25lOwogICAgY29sb3I6ICNkYzI2MjY7CiAgICBmb250LXNpemU6IDEzcHg7CiAgICBtYXJnaW4tdG9wOiAxMHB4OwogICAgdGV4dC1hbGlnbjogY2VudGVyOwogIH0KICAuY2hhbm5lbHMtaGludCB7CiAgICBiYWNrZ3JvdW5kOiAjZjhmYWZjOwogICAgYm9yZGVyLXJhZGl1czogOHB4OwogICAgcGFkZGluZzogMTJweDsKICAgIGZvbnQtc2l6ZTogMTJweDsKICAgIGNvbG9yOiAjNjQ3NDhiOwogICAgbWFyZ2luLWJvdHRvbTogMThweDsKICAgIGxpbmUtaGVpZ2h0OiAxLjY7CiAgfQo8L3N0eWxlPgo8L2hlYWQ+Cjxib2R5Pgo8ZGl2IGNsYXNzPSJjYXJkIiBpZD0iZm9ybUNhcmQiPgogIDxkaXYgY2xhc3M9ImxvZ28iPgogICAgPGgxPvCfjI8gVGhlIEdsb2JhbCBNYW5wb3dlcjwvaDE+CiAgICA8cD5JbW1pZ3JhdGlvbiBDb25zdWx0YXRpb24g4oCUIOC4peC4h+C4l+C4sOC5gOC4muC4teC4ouC4meC4o+C4seC4muC4hOC4s+C4m+C4o+C4tuC4geC4qeC4sjwvcD4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0iY2hhbm5lbHMtaGludCI+CiAgICDguIHguKPguLjguJPguLLguIHguKPguK3guIHguILguYnguK3guKHguLnguKXguJfguLXguYjguJXguLTguJTguJXguYjguK3guYTguJTguYnguKrguLDguJTguKfguIEg4LmA4Lie4Li34LmI4Lit4LmD4Lir4LmJ4LmA4Lij4Liy4Liq4Liy4Lih4Liy4Lij4LiW4LiV4Li04LiU4LiV4LmI4Lit4LmB4Lil4Liw4Liq4LmI4LiH4LmA4Lit4LiB4Liq4Liy4Lij4LiB4Lil4Lix4Lia4LiW4Li24LiH4LiE4Li44LiT4LmE4LiU4LmJ4LiX4Li44LiB4LiK4LmI4Lit4LiH4LiX4Liy4LiHCiAgPC9kaXY+CgogIDxmb3JtIGlkPSJsZWFkRm9ybSI+CiAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgPGxhYmVsPuC4iuC4t+C5iOC4rS3guJnguLLguKHguKrguIHguLjguKUgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4qPC9zcGFuPjwvbGFiZWw+CiAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBuYW1lPSJuYW1lIiByZXF1aXJlZCBwbGFjZWhvbGRlcj0i4LmA4LiK4LmI4LiZIOC4quC4oeC4iuC4suC4oiDguYPguIjguJTguLUiPgogICAgPC9kaXY+CgogICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgIDxsYWJlbD7guYDguJrguK3guKPguYzguYLguJfguKPguKjguLHguJ7guJfguYwgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4qPC9zcGFuPjwvbGFiZWw+CiAgICAgIDxpbnB1dCB0eXBlPSJ0ZWwiIG5hbWU9InBob25lIiByZXF1aXJlZCBwbGFjZWhvbGRlcj0i4LmA4LiK4LmI4LiZIDAyMTIzNDU2NzgiPgogICAgPC9kaXY+CgogICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgIDxsYWJlbD7guK3guLXguYDguKHguKUgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4qPC9zcGFuPjwvbGFiZWw+CiAgICAgIDxpbnB1dCB0eXBlPSJlbWFpbCIgbmFtZT0iZW1haWwiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPSJ5b3VyQGVtYWlsLmNvbSI+CiAgICA8L2Rpdj4KCiAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgPGxhYmVsPkxJTkUgSUQgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4ob3B0aW9uYWwpPC9zcGFuPjwvbGFiZWw+CiAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBuYW1lPSJsaW5lX2lkIiBwbGFjZWhvbGRlcj0iTElORSBJRCDguKvguKPguLfguK3guYDguJrguK3guKPguYzguJfguLXguYjguKXguIfguJfguLDguYDguJrguLXguKLguJkgTElORSI+CiAgICA8L2Rpdj4KCiAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgPGxhYmVsPkZhY2Vib29rIE1lc3NlbmdlciA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPihvcHRpb25hbCk8L3NwYW4+PC9sYWJlbD4KICAgICAgPGlucHV0IHR5cGU9InRleHQiIG5hbWU9Im1lc3Nlbmdlcl9pZCIgcGxhY2Vob2xkZXI9IuC4iuC4t+C5iOC4reC4muC4seC4jeC4iuC4tSBGYWNlYm9vayDguKvguKPguLfguK3guKXguLTguIfguIHguYzguYLguJvguKPguYTguJ/guKXguYwiPgogICAgPC9kaXY+CgogICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgIDxsYWJlbD5XaGF0c0FwcCA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPihvcHRpb25hbCk8L3NwYW4+PC9sYWJlbD4KICAgICAgPGlucHV0IHR5cGU9InRlbCIgbmFtZT0id2hhdHNhcHAiIHBsYWNlaG9sZGVyPSLguYDguJrguK3guKPguYwgV2hhdHNBcHAgKOC4o+C4p+C4oeC4o+C4q+C4seC4quC4m+C4o+C4sOC5gOC4l+C4qCkiPgogICAgPC9kaXY+CgogICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgIDxsYWJlbD7guKvguLHguKfguILguYnguK3guJfguLXguYjguJXguYnguK3guIfguIHguLLguKPguJvguKPguLbguIHguKnguLI8L2xhYmVsPgogICAgICA8c2VsZWN0IG5hbWU9InRvcGljIj4KICAgICAgICA8b3B0aW9uIHZhbHVlPSJ2aXNhIj7guILguK0gVmlzYSAvIOC4leC5iOC4rSBWaXNhPC9vcHRpb24+CiAgICAgICAgPG9wdGlvbiB2YWx1ZT0icmVzaWRlbmN5Ij7guJbguLTguYjguJnguJfguLXguYjguK3guKLguLnguYggKFJlc2lkZW5jeSk8L29wdGlvbj4KICAgICAgICA8b3B0aW9uIHZhbHVlPSJ3b3JrIj7guYPguJrguK3guJnguLjguI3guLLguJXguJfguLPguIfguLLguJk8L29wdGlvbj4KICAgICAgICA8b3B0aW9uIHZhbHVlPSJmYW1pbHkiPkZhbWlseSAvIFBhcnRuZXIgVmlzYTwvb3B0aW9uPgogICAgICAgIDxvcHRpb24gdmFsdWU9Im90aGVyIj7guK3guLfguYjguJnguYY8L29wdGlvbj4KICAgICAgPC9zZWxlY3Q+CiAgICA8L2Rpdj4KCiAgICA8YnV0dG9uIHR5cGU9InN1Ym1pdCIgY2xhc3M9ImJ0biIgaWQ9InN1Ym1pdEJ0biI+4Liq4LmI4LiH4LiC4LmJ4Lit4Lih4Li54LilPC9idXR0b24+CiAgICA8ZGl2IGNsYXNzPSJlcnJvci1tc2ciIGlkPSJlcnJvck1zZyI+PC9kaXY+CiAgPC9mb3JtPgoKICA8ZGl2IGNsYXNzPSJub3RlIj4KICAgIOC4guC5ieC4reC4oeC4ueC4peC4guC4reC4h+C4hOC4uOC4k+C4iOC4sOC4luC4ueC4geC5gOC4geC5h+C4muC5gOC4m+C5h+C4meC4hOC4p+C4suC4oeC4peC4seC4muC5geC4peC4sOC5g+C4iuC5ieC4quC4s+C4q+C4o+C4seC4muC4geC4suC4o+C5g+C4q+C5ieC4hOC4s+C4m+C4o+C4tuC4geC4qeC4suC5gOC4l+C5iOC4suC4meC4seC5ieC4mQogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0gU3VjY2VzcyBTY3JlZW4gLS0+CjxkaXYgY2xhc3M9ImNhcmQiIGlkPSJzdWNjZXNzQ2FyZCIgc3R5bGU9ImRpc3BsYXk6bm9uZTsiPgogIDxkaXYgY2xhc3M9InN1Y2Nlc3MiPgogICAgPGRpdiBjbGFzcz0iY2hlY2siPuKchTwvZGl2PgogICAgPGgyPuC4quC5iOC4h+C4guC5ieC4reC4oeC4ueC4peC4quC4s+C5gOC4o+C5h+C4iCE8L2gyPgogICAgPHA+4LmA4Lij4Liy4LiI4Liw4LiV4Li04LiU4LiV4LmI4Lit4LiB4Lil4Lix4Lia4LmC4LiU4Lii4LmA4Lij4LmH4Lin4LiX4Li14LmI4Liq4Li44LiU4LiX4Liy4LiH4LiK4LmI4Lit4LiH4LiX4Liy4LiH4LiX4Li14LmI4LiE4Li44LiT4LmA4Lil4Li34Lit4LiB4LmE4Lin4LmJPGJyPuC4guC4reC4muC4hOC4uOC4k+C4l+C4teC5iOC5g+C4iuC5ieC4muC4o+C4tOC4geC4suC4oyBUaGUgR2xvYmFsIE1hbnBvd2VyPC9wPgogIDwvZGl2Pgo8L2Rpdj4KCjxzY3JpcHQ+CmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsZWFkRm9ybScpLmFkZEV2ZW50TGlzdGVuZXIoJ3N1Ym1pdCcsIGFzeW5jIGZ1bmN0aW9uKGUpIHsKICBlLnByZXZlbnREZWZhdWx0KCk7CiAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N1Ym1pdEJ0bicpOwogIGNvbnN0IGVyckVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Vycm9yTXNnJyk7CiAgYnRuLmRpc2FibGVkID0gdHJ1ZTsKICBidG4udGV4dENvbnRlbnQgPSAn4LiB4Liz4Lil4Lix4LiH4Liq4LmI4LiHLi4uJzsKICBlcnJFbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwoKICBjb25zdCBmb3JtRGF0YSA9IG5ldyBGb3JtRGF0YSh0aGlzKTsKICBjb25zdCBkYXRhID0gT2JqZWN0LmZyb21FbnRyaWVzKGZvcm1EYXRhLmVudHJpZXMoKSk7CgogIHRyeSB7CiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2xhbmRpbmcvc3VibWl0JywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeyAnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nIH0sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KGRhdGEpCiAgICB9KTsKCiAgICBpZiAoIXJlcy5vaykgewogICAgICBjb25zdCB0ZXh0ID0gYXdhaXQgcmVzLnRleHQoKTsKICAgICAgdGhyb3cgbmV3IEVycm9yKHRleHQgfHwgJ+C4quC5iOC4h+C4guC5ieC4reC4oeC4ueC4peC5hOC4oeC5iOC4quC4s+C5gOC4o+C5h+C4iCcpOwogICAgfQoKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmb3JtQ2FyZCcpLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3VjY2Vzc0NhcmQnKS5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICB9IGNhdGNoIChlcnIpIHsKICAgIGVyckVsLnRleHRDb250ZW50ID0gJ+C5gOC4geC4tOC4lOC4guC5ieC4reC4nOC4tOC4lOC4nuC4peC4suC4lDogJyArIGVyci5tZXNzYWdlICsgJyDguIHguKPguLjguJPguLLguKXguK3guIfguK3guLXguIHguITguKPguLHguYnguIcnOwogICAgZXJyRWwuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBidG4uZGlzYWJsZWQgPSBmYWxzZTsKICAgIGJ0bi50ZXh0Q29udGVudCA9ICfguKrguYjguIfguILguYnguK3guKHguLnguKUnOwogIH0KfSk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K").decode("utf-8")


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
