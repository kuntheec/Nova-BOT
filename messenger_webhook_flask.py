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


LANDING_HTML = base64.b64decode("PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9InRoIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+VGhlIEdsb2JhbCBNYW5wb3dlciDigJQgSW1taWdyYXRpb24gU2VydmljZXM8L3RpdGxlPgo8c3R5bGU+CiAgKiB7IGJveC1zaXppbmc6IGJvcmRlci1ib3g7IG1hcmdpbjogMDsgcGFkZGluZzogMDsgfQogIGJvZHkgewogICAgZm9udC1mYW1pbHk6IC1hcHBsZS1zeXN0ZW0sIEJsaW5rTWFjU3lzdGVtRm9udCwgJ1NlZ29lIFVJJywgc2Fucy1zZXJpZjsKICAgIGJhY2tncm91bmQ6IGxpbmVhci1ncmFkaWVudCgxMzVkZWcsICMwZjE3MmEgMCUsICMxZTI5M2IgMTAwJSk7CiAgICBtaW4taGVpZ2h0OiAxMDB2aDsKICAgIGRpc3BsYXk6IGZsZXg7CiAgICBhbGlnbi1pdGVtczogY2VudGVyOwogICAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7CiAgICBwYWRkaW5nOiAyMHB4OwogIH0KICAuY2FyZCB7CiAgICBiYWNrZ3JvdW5kOiAjZmZmOwogICAgYm9yZGVyLXJhZGl1czogMTZweDsKICAgIHBhZGRpbmc6IDQwcHg7CiAgICBtYXgtd2lkdGg6IDUyMHB4OwogICAgd2lkdGg6IDEwMCU7CiAgICBib3gtc2hhZG93OiAwIDIwcHggNjBweCByZ2JhKDAsMCwwLDAuMyk7CiAgfQogIC5sb2dvIHsgdGV4dC1hbGlnbjogY2VudGVyOyBtYXJnaW4tYm90dG9tOiAyNHB4OyB9CiAgLmxvZ28gaDEgeyBmb250LXNpemU6IDIycHg7IGNvbG9yOiAjMWUyOTNiOyBtYXJnaW4tYm90dG9tOiA0cHg7IH0KICAubG9nbyBwIHsgZm9udC1zaXplOiAxNHB4OyBjb2xvcjogIzY0NzQ4YjsgfQogIC5mb3JtLWdyb3VwIHsgbWFyZ2luLWJvdHRvbTogMThweDsgfQogIGxhYmVsIHsgZGlzcGxheTogYmxvY2s7IGZvbnQtc2l6ZTogMTNweDsgZm9udC13ZWlnaHQ6IDYwMDsgY29sb3I6ICMzMzQxNTU7IG1hcmdpbi1ib3R0b206IDZweDsgfQogIGxhYmVsIC5vcHRpb25hbCB7IGZvbnQtd2VpZ2h0OiA0MDA7IGNvbG9yOiAjOTRhM2I4OyBmb250LXNpemU6IDEycHg7IH0KICBpbnB1dCwgc2VsZWN0IHsKICAgIHdpZHRoOiAxMDAlOyBwYWRkaW5nOiAxMnB4IDE0cHg7CiAgICBib3JkZXI6IDEuNXB4IHNvbGlkICNlMmU4ZjA7IGJvcmRlci1yYWRpdXM6IDEwcHg7CiAgICBmb250LXNpemU6IDE1cHg7IHRyYW5zaXRpb246IGJvcmRlci1jb2xvciAwLjJzOyBvdXRsaW5lOiBub25lOwogIH0KICBpbnB1dDpmb2N1cywgc2VsZWN0OmZvY3VzIHsgYm9yZGVyLWNvbG9yOiAjM2I4MmY2OyBib3gtc2hhZG93OiAwIDAgMCAzcHggcmdiYSg1OSwxMzAsMjQ2LDAuMTUpOyB9CiAgLmlucHV0LXJvdyB7IGRpc3BsYXk6IGZsZXg7IGdhcDogOHB4OyB9CiAgLmlucHV0LXJvdyBpbnB1dCB7IGZsZXg6IDE7IH0KICAuYnRuIHsKICAgIHBhZGRpbmc6IDEycHggMjBweDsgYmFja2dyb3VuZDogIzI1NjNlYjsgY29sb3I6ICNmZmY7CiAgICBib3JkZXI6IG5vbmU7IGJvcmRlci1yYWRpdXM6IDEwcHg7IGZvbnQtc2l6ZTogMTRweDsgZm9udC13ZWlnaHQ6IDYwMDsKICAgIGN1cnNvcjogcG9pbnRlcjsgdHJhbnNpdGlvbjogYmFja2dyb3VuZCAwLjJzOyB3aGl0ZS1zcGFjZTogbm93cmFwOwogIH0KICAuYnRuOmhvdmVyIHsgYmFja2dyb3VuZDogIzFkNGVkODsgfQogIC5idG46ZGlzYWJsZWQgeyBvcGFjaXR5OiAwLjY7IGN1cnNvcjogbm90LWFsbG93ZWQ7IH0KICAuYnRuLXNtIHsgcGFkZGluZzogMTBweCAxNnB4OyBmb250LXNpemU6IDEzcHg7IGJvcmRlci1yYWRpdXM6IDhweDsgfQogIC5idG4tZ3JlZW4geyBiYWNrZ3JvdW5kOiAjMTZhMzRhOyB9CiAgLmJ0bi1ncmVlbjpob3ZlciB7IGJhY2tncm91bmQ6ICMxNTgwM2Q7IH0KICAuYnRuLWZ1bGwgeyB3aWR0aDogMTAwJTsgcGFkZGluZzogMTRweDsgZm9udC1zaXplOiAxNnB4OyBtYXJnaW4tdG9wOiA4cHg7IH0KICAuYnRuLWdyYXkgeyBiYWNrZ3JvdW5kOiAjNjQ3NDhiOyB9CiAgLmJ0bi1ncmF5OmhvdmVyIHsgYmFja2dyb3VuZDogIzQ3NTU2OTsgfQoKICAudmVyaWZ5LXN0YXR1cyB7CiAgICBkaXNwbGF5OiBub25lOyBwYWRkaW5nOiAxMHB4IDE0cHg7IGJvcmRlci1yYWRpdXM6IDhweDsKICAgIGZvbnQtc2l6ZTogMTNweDsgbWFyZ2luLXRvcDogOHB4OwogIH0KICAudmVyaWZ5LW9rIHsgZGlzcGxheTogYmxvY2s7IGJhY2tncm91bmQ6ICNkY2ZjZTc7IGNvbG9yOiAjMTZhMzRhOyBib3JkZXI6IDFweCBzb2xpZCAjYmJmN2QwOyB9CiAgLnZlcmlmeS1lcnIgeyBkaXNwbGF5OiBibG9jazsgYmFja2dyb3VuZDogI2ZlZjJmMjsgY29sb3I6ICNkYzI2MjY7IGJvcmRlcjogMXB4IHNvbGlkICNmZWNhY2E7IH0KICAudmVyaWZ5LWxvYWRpbmcgeyBkaXNwbGF5OiBibG9jazsgYmFja2dyb3VuZDogI2Y4ZmFmYzsgY29sb3I6ICM2NDc0OGI7IGJvcmRlcjogMXB4IHNvbGlkICNlMmU4ZjA7IH0KCiAgLnN0ZXAtaW5kaWNhdG9yIHsKICAgIGRpc3BsYXk6IGZsZXg7IGdhcDogOHB4OyBtYXJnaW4tYm90dG9tOiAyNHB4OyBqdXN0aWZ5LWNvbnRlbnQ6IGNlbnRlcjsKICB9CiAgLnN0ZXAgewogICAgd2lkdGg6IDMycHg7IGhlaWdodDogMzJweDsgYm9yZGVyLXJhZGl1czogNTAlOwogICAgZGlzcGxheTogZmxleDsgYWxpZ24taXRlbXM6IGNlbnRlcjsganVzdGlmeS1jb250ZW50OiBjZW50ZXI7CiAgICBmb250LXNpemU6IDEzcHg7IGZvbnQtd2VpZ2h0OiA2MDA7CiAgfQogIC5zdGVwLWFjdGl2ZSB7IGJhY2tncm91bmQ6ICMyNTYzZWI7IGNvbG9yOiAjZmZmOyB9CiAgLnN0ZXAtZG9uZSB7IGJhY2tncm91bmQ6ICMxNmEzNGE7IGNvbG9yOiAjZmZmOyB9CiAgLnN0ZXAtcGVuZGluZyB7IGJhY2tncm91bmQ6ICNlMmU4ZjA7IGNvbG9yOiAjOTRhM2I4OyB9CiAgLnN0ZXAtbGluZSB7IHdpZHRoOiA0MHB4OyBoZWlnaHQ6IDJweDsgYWxpZ24tc2VsZjogY2VudGVyOyBiYWNrZ3JvdW5kOiAjZTJlOGYwOyB9CiAgLnN0ZXAtbGluZS1kb25lIHsgYmFja2dyb3VuZDogIzE2YTM0YTsgfQoKICAubG9ja2VkIHsgb3BhY2l0eTogMC41OyBwb2ludGVyLWV2ZW50czogbm9uZTsgfQogIC5oaWRkZW4tc2VjdGlvbiB7IGRpc3BsYXk6IG5vbmU7IH0KCiAgLm5vdGUgewogICAgZm9udC1zaXplOiAxMnB4OyBjb2xvcjogIzY0NzQ4YjsgdGV4dC1hbGlnbjogY2VudGVyOyBtYXJnaW4tdG9wOiAyMHB4OyBsaW5lLWhlaWdodDogMS41OwogIH0KICAuc3VjY2VzcyB7CiAgICBkaXNwbGF5OiBub25lOyB0ZXh0LWFsaWduOiBjZW50ZXI7IHBhZGRpbmc6IDMwcHggMDsKICB9CiAgLnN1Y2Nlc3MgLmNoZWNrIHsgZm9udC1zaXplOiA0OHB4OyBtYXJnaW4tYm90dG9tOiAxMnB4OyB9CiAgLnN1Y2Nlc3MgaDIgeyBjb2xvcjogIzE2YTM0YTsgbWFyZ2luLWJvdHRvbTogOHB4OyB9CiAgLnN1Y2Nlc3MgcCB7IGNvbG9yOiAjNjQ3NDhiOyBmb250LXNpemU6IDE0cHg7IGxpbmUtaGVpZ2h0OiAxLjY7IH0KICAuZXJyb3ItbXNnIHsgZGlzcGxheTogbm9uZTsgY29sb3I6ICNkYzI2MjY7IGZvbnQtc2l6ZTogMTNweDsgbWFyZ2luLXRvcDogMTBweDsgdGV4dC1hbGlnbjogY2VudGVyOyB9CiAgLmNoYW5uZWxzLWhpbnQgewogICAgYmFja2dyb3VuZDogI2Y4ZmFmYzsgYm9yZGVyLXJhZGl1czogOHB4OyBwYWRkaW5nOiAxMnB4OwogICAgZm9udC1zaXplOiAxMnB4OyBjb2xvcjogIzY0NzQ4YjsgbWFyZ2luLWJvdHRvbTogMThweDsgbGluZS1oZWlnaHQ6IDEuNjsKICB9Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+Cgo8ZGl2IGNsYXNzPSJjYXJkIiBpZD0iZm9ybUNhcmQiPgogIDxkaXYgY2xhc3M9ImxvZ28iPgogICAgPGgxPlRoZSBHbG9iYWwgTWFucG93ZXI8L2gxPgogICAgPHA+SW1taWdyYXRpb24gQ29uc3VsdGF0aW9uIOKAlCDguKXguIfguJfguLDguYDguJrguLXguKLguJnguKPguLHguJrguITguLPguJvguKPguLbguIHguKnguLI8L3A+CiAgPC9kaXY+CgogIDwhLS0gU3RlcCBJbmRpY2F0b3IgLS0+CiAgPGRpdiBjbGFzcz0ic3RlcC1pbmRpY2F0b3IiPgogICAgPGRpdiBjbGFzcz0ic3RlcCBzdGVwLWFjdGl2ZSIgaWQ9InN0ZXAxIj4xPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzdGVwLWxpbmUiIGlkPSJsaW5lMSI+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzdGVwIHN0ZXAtcGVuZGluZyIgaWQ9InN0ZXAyIj4yPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzdGVwLWxpbmUiIGlkPSJsaW5lMiI+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzdGVwIHN0ZXAtcGVuZGluZyIgaWQ9InN0ZXAzIj4zPC9kaXY+CiAgPC9kaXY+CgogIDxkaXYgaWQ9ImVycm9yVG9wIiBjbGFzcz0iZXJyb3ItbXNnIj48L2Rpdj4KCiAgPCEtLSBTVEVQIDE6IEVtYWlsIFZlcmlmaWNhdGlvbiAtLT4KICA8ZGl2IGlkPSJzdGVwMUNvbnRlbnQiPgogICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgIDxsYWJlbD7guK3guLXguYDguKHguKUgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4qPC9zcGFuPjwvbGFiZWw+CiAgICAgIDxkaXYgY2xhc3M9ImlucHV0LXJvdyI+CiAgICAgICAgPGlucHV0IHR5cGU9ImVtYWlsIiBpZD0idmVyaWZ5RW1haWwiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPSJ5b3VyQGVtYWlsLmNvbSI+CiAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGJ0bi1zbSIgaWQ9InNlbmRDb2RlQnRuIiBvbmNsaWNrPSJzZW5kQ29kZSgpIj7guKrguYjguIfguKPguKvguLHguKo8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgaWQ9InZlcmlmeVN0YXR1cyIgY2xhc3M9InZlcmlmeS1zdGF0dXMiPjwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiIHN0eWxlPSJkaXNwbGF5Om5vbmU7IiBpZD0iY29kZUdyb3VwIj4KICAgICAgPGxhYmVsPuC4o+C4q+C4seC4quC4ouC4t+C4meC4ouC4seC4mSA2IOC4q+C4peC4seC4gTwvbGFiZWw+CiAgICAgIDxkaXYgY2xhc3M9ImlucHV0LXJvdyI+CiAgICAgICAgPGlucHV0IHR5cGU9InRleHQiIGlkPSJjb2RlSW5wdXQiIG1heGxlbmd0aD0iNiIgcGxhY2Vob2xkZXI9IjAwMDAwMCIgaW5wdXRtb2RlPSJudW1lcmljIiBwYXR0ZXJuPSJbMC05XSoiPgogICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBidG4tc20gYnRuLWdyZWVuIiBpZD0idmVyaWZ5Q29kZUJ0biIgb25jbGljaz0idmVyaWZ5Q29kZSgpIj7guKLguLfguJnguKLguLHguJk8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KCiAgPCEtLSBTVEVQIDI6IFBlcnNvbmFsIEluZm8gLS0+CiAgPGRpdiBpZD0ic3RlcDJDb250ZW50IiBzdHlsZT0iZGlzcGxheTpub25lOyI+CiAgICA8ZGl2IGNsYXNzPSJjaGFubmVscy1oaW50Ij4KICAgICAg4pyFIOC4ouC4t+C4meC4ouC4seC4meC4reC4teC5gOC4oeC4peC5gOC4o+C4teC4ouC4muC4o+C5ieC4reC4ouC5geC4peC5ieC4pzxicj4KICAgICAgPHN0cm9uZz7wn5OdIOC4luC5ieC4suC4peC4h+C4l+C4sOC5gOC4muC4teC4ouC4meC5geC4peC5ieC4pyDigJQg4LiB4Lij4Lit4LiB4Lit4Li14LmA4Lih4Lil4LmA4LiU4Li04LihIOC4o+C4sOC4muC4muC4iOC4sOC4reC4seC4m+C5gOC4lOC4leC4guC5ieC4reC4oeC4ueC4peC5g+C4q+C5ieC4reC4seC4leC5guC4meC4oeC4seC4leC4tDwvc3Ryb25nPgogICAgPC9kaXY+CgogICAgPGZvcm0gaWQ9ImxlYWRGb3JtIj4KICAgICAgPGlucHV0IHR5cGU9ImhpZGRlbiIgbmFtZT0iZW1haWwiIGlkPSJoaWRkZW5FbWFpbCIgdmFsdWU9IiI+CgogICAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgICA8bGFiZWw+4LiK4Li34LmI4LitLeC4meC4suC4oeC4quC4geC4uOC4pSA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPio8L3NwYW4+PC9sYWJlbD4KICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgbmFtZT0ibmFtZSIgcmVxdWlyZWQgcGxhY2Vob2xkZXI9IuC5gOC4iuC5iOC4mSDguKrguKHguIrguLLguKIg4LmD4LiI4LiU4Li1Ij4KICAgICAgPC9kaXY+CgogICAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgICA8bGFiZWw+4LmA4Lia4Lit4Lij4LmM4LmC4LiX4Lij4Lio4Lix4Lie4LiX4LmMIDxzcGFuIGNsYXNzPSJvcHRpb25hbCI+Kjwvc3Bhbj48L2xhYmVsPgogICAgICAgIDxpbnB1dCB0eXBlPSJ0ZWwiIG5hbWU9InBob25lIiByZXF1aXJlZCBwbGFjZWhvbGRlcj0i4LmA4LiK4LmI4LiZIDAyMTIzNDU2NzgiPgogICAgICA8L2Rpdj4KCiAgICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPgogICAgICAgIDxsYWJlbD5MSU5FIElEIDxzcGFuIGNsYXNzPSJvcHRpb25hbCI+KG9wdGlvbmFsKTwvc3Bhbj48L2xhYmVsPgogICAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBuYW1lPSJsaW5lX2lkIiBwbGFjZWhvbGRlcj0iTElORSBJRCDguKvguKPguLfguK3guYDguJrguK3guKPguYzguJfguLXguYjguKXguIfguJfguLDguYDguJrguLXguKLguJkgTElORSI+CiAgICAgIDwvZGl2PgoKICAgICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgICAgPGxhYmVsPkZhY2Vib29rIE1lc3NlbmdlciA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPihvcHRpb25hbCk8L3NwYW4+PC9sYWJlbD4KICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgbmFtZT0ibWVzc2VuZ2VyX2lkIiBwbGFjZWhvbGRlcj0i4LiK4Li34LmI4Lit4Lia4Lix4LiN4LiK4Li1IEZhY2Vib29rIj4KICAgICAgPC9kaXY+CgogICAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgICA8bGFiZWw+V2hhdHNBcHAgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4ob3B0aW9uYWwpPC9zcGFuPjwvbGFiZWw+CiAgICAgICAgPGlucHV0IHR5cGU9InRlbCIgbmFtZT0id2hhdHNhcHAiIHBsYWNlaG9sZGVyPSLguYDguJrguK3guKPguYwgV2hhdHNBcHAgKOC4o+C4p+C4oeC4o+C4q+C4seC4quC4m+C4o+C4sOC5gOC4l+C4qCkiPgogICAgICA8L2Rpdj4KCiAgICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPgogICAgICAgIDxsYWJlbD7guKvguLHguKfguILguYnguK3guJfguLXguYjguJXguYnguK3guIfguIHguLLguKPguJvguKPguLbguIHguKnguLI8L2xhYmVsPgogICAgICAgIDxzZWxlY3QgbmFtZT0idG9waWMiPgogICAgICAgICAgPG9wdGlvbiB2YWx1ZT0idmlzYSI+4LiC4LitIFZpc2EgLyDguJXguYjguK0gVmlzYTwvb3B0aW9uPgogICAgICAgICAgPG9wdGlvbiB2YWx1ZT0icmVzaWRlbmN5Ij7guJbguLTguYjguJnguJfguLXguYjguK3guKLguLnguYggKFJlc2lkZW5jeSk8L29wdGlvbj4KICAgICAgICAgIDxvcHRpb24gdmFsdWU9IndvcmsiPuC5g+C4muC4reC4meC4uOC4jeC4suC4leC4l+C4s+C4h+C4suC4mTwvb3B0aW9uPgogICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iZmFtaWx5Ij5GYW1pbHkgLyBQYXJ0bmVyIFZpc2E8L29wdGlvbj4KICAgICAgICAgIDxvcHRpb24gdmFsdWU9Im90aGVyIj7guK3guLfguYjguJnguYY8L29wdGlvbj4KICAgICAgICA8L3NlbGVjdD4KICAgICAgPC9kaXY+CgogICAgICA8YnV0dG9uIHR5cGU9InN1Ym1pdCIgY2xhc3M9ImJ0biBidG4tZnVsbCIgaWQ9InN1Ym1pdEJ0biI+4Liq4LmI4LiH4LiC4LmJ4Lit4Lih4Li54LilPC9idXR0b24+CiAgICAgIDxkaXYgY2xhc3M9ImVycm9yLW1zZyIgaWQ9ImZvcm1FcnJvciI+PC9kaXY+CiAgICA8L2Zvcm0+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9Im5vdGUiPgogICAg4LiC4LmJ4Lit4Lih4Li54Lil4LiC4Lit4LiH4LiE4Li44LiT4LiI4Liw4LiW4Li54LiB4LmA4LiB4LmH4Lia4LmA4Lib4LmH4LiZ4LiE4Lin4Liy4Lih4Lil4Lix4Lia4LmB4Lil4Liw4LmD4LiK4LmJ4Liq4Liz4Lir4Lij4Lix4Lia4LiB4Liy4Lij4LmD4Lir4LmJ4LiE4Liz4Lib4Lij4Li24LiB4Lip4Liy4LmA4LiX4LmI4Liy4LiZ4Lix4LmJ4LiZCiAgPC9kaXY+CjwvZGl2PgoKPCEtLSBTdWNjZXNzIFNjcmVlbiAtLT4KPGRpdiBjbGFzcz0iY2FyZCIgaWQ9InN1Y2Nlc3NDYXJkIiBzdHlsZT0iZGlzcGxheTpub25lOyI+CiAgPGRpdiBjbGFzcz0ic3VjY2VzcyIgc3R5bGU9ImRpc3BsYXk6YmxvY2s7Ij4KICAgIDxkaXYgY2xhc3M9ImNoZWNrIj7inIU8L2Rpdj4KICAgIDxoMj7guKrguYjguIfguILguYnguK3guKHguLnguKXguKrguLPguYDguKPguYfguIghPC9oMj4KICAgIDxwPuC5gOC4o+C4suC4iOC4sOC4leC4tOC4lOC4leC5iOC4reC4geC4peC4seC4muC5guC4lOC4ouC5gOC4o+C5h+C4p+C4l+C4teC5iOC4quC4uOC4lOC4l+C4suC4h+C4iuC5iOC4reC4h+C4l+C4suC4h+C4l+C4teC5iOC4hOC4uOC4k+C5gOC4peC4t+C4reC4geC5hOC4p+C5iTxicj7guILguK3guJrguITguLjguJPguJfguLXguYjguYPguIrguYnguJrguKPguLTguIHguLLguKMgVGhlIEdsb2JhbCBNYW5wb3dlcjwvcD4KICA8L2Rpdj4KPC9kaXY+Cgo8c2NyaXB0PgpsZXQgdmVyaWZpZWRFbWFpbCA9ICcnOwoKYXN5bmMgZnVuY3Rpb24gc2VuZENvZGUoKSB7CiAgY29uc3QgZW1haWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5RW1haWwnKS52YWx1ZS50cmltKCk7CiAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmRDb2RlQnRuJyk7CiAgY29uc3Qgc3RhdHVzID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlcmlmeVN0YXR1cycpOwoKICBpZiAoIWVtYWlsIHx8ICFlbWFpbC5pbmNsdWRlcygnQCcpKSB7CiAgICBzdGF0dXMuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMgdmVyaWZ5LWVycic7CiAgICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4LiB4Lij4Li44LiT4Liy4LiB4Lij4Lit4LiB4Lit4Li14LmA4Lih4Lil4LiX4Li14LmI4LiW4Li54LiB4LiV4LmJ4Lit4LiHJzsKICAgIHJldHVybjsKICB9CgogIGJ0bi5kaXNhYmxlZCA9IHRydWU7CiAgYnRuLnRleHRDb250ZW50ID0gJ+C4geC4s+C4peC4seC4h+C4quC5iOC4hy4uLic7CiAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1sb2FkaW5nJzsKICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4LiB4Liz4Lil4Lix4LiH4Liq4LmI4LiH4Lij4Lir4Lix4Liq4Lii4Li34LiZ4Lii4Lix4LiZ4LmE4Lib4Lii4Lix4LiH4Lit4Li14LmA4Lih4LilLi4uJzsKCiAgdHJ5IHsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvbGFuZGluZy9zZW5kLWNvZGUnLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoeyBlbWFpbCB9KQogICAgfSk7CiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzLmpzb24oKTsKCiAgICBpZiAocmVzLm9rKSB7CiAgICAgIHN0YXR1cy5jbGFzc05hbWUgPSAndmVyaWZ5LXN0YXR1cyB2ZXJpZnktb2snOwogICAgICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4pyFIOC4quC5iOC4h+C4o+C4q+C4seC4quC5hOC4m+C4ouC4seC4h+C4reC4teC5gOC4oeC4peC4guC4reC4h+C4hOC4uOC4k+C5geC4peC5ieC4pyDguIHguKPguLjguJPguLLguJXguKPguKfguIjguKrguK3guJrguK3guLXguYDguKHguKUnOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29kZUdyb3VwJykuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlFbWFpbCcpLnJlYWRPbmx5ID0gdHJ1ZTsKICAgICAgYnRuLnRleHRDb250ZW50ID0gJ+C4quC5iOC4h+C4reC4teC4geC4hOC4o+C4seC5ieC4hyc7CiAgICAgIGJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29kZUlucHV0JykuZm9jdXMoKTsKICAgIH0gZWxzZSB7CiAgICAgIHN0YXR1cy5jbGFzc05hbWUgPSAndmVyaWZ5LXN0YXR1cyB2ZXJpZnktZXJyJzsKICAgICAgc3RhdHVzLnRleHRDb250ZW50ID0gJ+KdjCAnICsgKGRhdGEuZXJyb3IgfHwgJ+C4quC5iOC4h+C4o+C4q+C4seC4quC5hOC4oeC5iOC4quC4s+C5gOC4o+C5h+C4iCcpOwogICAgICBidG4uZGlzYWJsZWQgPSBmYWxzZTsKICAgICAgYnRuLnRleHRDb250ZW50ID0gJ+C4quC5iOC4h+C4o+C4q+C4seC4qic7CiAgICB9CiAgfSBjYXRjaCAoZXJyKSB7CiAgICBzdGF0dXMuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMgdmVyaWZ5LWVycic7CiAgICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4p2MIOC5gOC4geC4tOC4lOC4guC5ieC4reC4nOC4tOC4lOC4nuC4peC4suC4lCDguIHguKPguLjguJPguLLguKXguK3guIfguYPguKvguKHguYgnOwogICAgYnRuLmRpc2FibGVkID0gZmFsc2U7CiAgICBidG4udGV4dENvbnRlbnQgPSAn4Liq4LmI4LiH4Lij4Lir4Lix4LiqJzsKICB9Cn0KCmFzeW5jIGZ1bmN0aW9uIHZlcmlmeUNvZGUoKSB7CiAgY29uc3QgZW1haWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5RW1haWwnKS52YWx1ZS50cmltKCk7CiAgY29uc3QgY29kZSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb2RlSW5wdXQnKS52YWx1ZS50cmltKCk7CiAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlcmlmeUNvZGVCdG4nKTsKICBjb25zdCBzdGF0dXMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5U3RhdHVzJyk7CgogIGlmICghY29kZSB8fCBjb2RlLmxlbmd0aCAhPT0gNikgewogICAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1lcnInOwogICAgc3RhdHVzLnRleHRDb250ZW50ID0gJ+C4geC4o+C4uOC4k+C4suC4geC4o+C4reC4geC4o+C4q+C4seC4quC4ouC4t+C4meC4ouC4seC4mSA2IOC4q+C4peC4seC4gSc7CiAgICByZXR1cm47CiAgfQoKICBidG4uZGlzYWJsZWQgPSB0cnVlOwogIGJ0bi50ZXh0Q29udGVudCA9ICfguIHguLPguKXguLHguIfguJXguKPguKfguIjguKrguK3guJouLi4nOwogIHN0YXR1cy5jbGFzc05hbWUgPSAndmVyaWZ5LXN0YXR1cyB2ZXJpZnktbG9hZGluZyc7CiAgc3RhdHVzLnRleHRDb250ZW50ID0gJ+C4geC4s+C4peC4seC4h+C4leC4o+C4p+C4iOC4quC4reC4muC4o+C4q+C4seC4qi4uLic7CgogIHRyeSB7CiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2xhbmRpbmcvdmVyaWZ5LWNvZGUnLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoeyBlbWFpbCwgY29kZSB9KQogICAgfSk7CiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzLmpzb24oKTsKCiAgICBpZiAocmVzLm9rKSB7CiAgICAgIHZlcmlmaWVkRW1haWwgPSBlbWFpbDsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2hpZGRlbkVtYWlsJykudmFsdWUgPSBlbWFpbDsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0ZXAxJykuY2xhc3NOYW1lID0gJ3N0ZXAgc3RlcC1kb25lJzsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0ZXAxJykudGV4dENvbnRlbnQgPSAn4pyTJzsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2xpbmUxJykuY2xhc3NOYW1lID0gJ3N0ZXAtbGluZSBzdGVwLWxpbmUtZG9uZSc7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGVwMicpLmNsYXNzTmFtZSA9ICdzdGVwIHN0ZXAtYWN0aXZlJzsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0ZXAyJykudGV4dENvbnRlbnQgPSAnMic7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGVwMUNvbnRlbnQnKS5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RlcDJDb250ZW50Jykuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICB9IGVsc2UgewogICAgICBzdGF0dXMuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMgdmVyaWZ5LWVycic7CiAgICAgIHN0YXR1cy50ZXh0Q29udGVudCA9ICfinYwgJyArIChkYXRhLmVycm9yIHx8ICfguKPguKvguLHguKrguYTguKHguYjguJbguLnguIHguJXguYnguK3guIcnKTsKICAgICAgYnRuLmRpc2FibGVkID0gZmFsc2U7CiAgICAgIGJ0bi50ZXh0Q29udGVudCA9ICfguKLguLfguJnguKLguLHguJknOwogICAgfQogIH0gY2F0Y2ggKGVycikgewogICAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1lcnInOwogICAgc3RhdHVzLnRleHRDb250ZW50ID0gJ+KdjCDguYDguIHguLTguJTguILguYnguK3guJzguLTguJTguJ7guKXguLLguJQg4LiB4Lij4Li44LiT4Liy4Lil4Lit4LiH4LmD4Lir4Lih4LmIJzsKICAgIGJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgYnRuLnRleHRDb250ZW50ID0gJ+C4ouC4t+C4meC4ouC4seC4mSc7CiAgfQp9Cgpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbGVhZEZvcm0nKS5hZGRFdmVudExpc3RlbmVyKCdzdWJtaXQnLCBhc3luYyBmdW5jdGlvbihlKSB7CiAgZS5wcmV2ZW50RGVmYXVsdCgpOwogIGNvbnN0IGJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdWJtaXRCdG4nKTsKICBjb25zdCBlcnJFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmb3JtRXJyb3InKTsKICBidG4uZGlzYWJsZWQgPSB0cnVlOwogIGJ0bi50ZXh0Q29udGVudCA9ICfguIHguLPguKXguLHguIfguKrguYjguIcuLi4nOwogIGVyckVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CgogIGNvbnN0IGZvcm1EYXRhID0gbmV3IEZvcm1EYXRhKHRoaXMpOwogIGNvbnN0IGRhdGEgPSBPYmplY3QuZnJvbUVudHJpZXMoZm9ybURhdGEuZW50cmllcygpKTsKICBkYXRhLmVtYWlsID0gdmVyaWZpZWRFbWFpbDsKCiAgdHJ5IHsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvbGFuZGluZy9zdWJtaXQnLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoZGF0YSkKICAgIH0pOwoKICAgIGlmICghcmVzLm9rKSB7CiAgICAgIGNvbnN0IHRleHQgPSBhd2FpdCByZXMudGV4dCgpOwogICAgICB0aHJvdyBuZXcgRXJyb3IodGV4dCB8fCAn4Liq4LmI4LiH4LiC4LmJ4Lit4Lih4Li54Lil4LmE4Lih4LmI4Liq4Liz4LmA4Lij4LmH4LiIJyk7CiAgICB9CgogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Zvcm1DYXJkJykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdWNjZXNzQ2FyZCcpLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogIH0gY2F0Y2ggKGVycikgewogICAgZXJyRWwudGV4dENvbnRlbnQgPSAn4LmA4LiB4Li04LiU4LiC4LmJ4Lit4Lic4Li04LiU4Lie4Lil4Liy4LiUOiAnICsgZXJyLm1lc3NhZ2UgKyAnIOC4geC4o+C4uOC4k+C4suC4peC4reC4h+C4reC4teC4geC4hOC4o+C4seC5ieC4hyc7CiAgICBlcnJFbC5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICAgIGJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgYnRuLnRleHRDb250ZW50ID0gJ+C4quC5iOC4h+C4guC5ieC4reC4oeC4ueC4pSc7CiAgfQp9KTsKCi8vIEVudGVyIGtleSB0cmlnZ2VycyBuZXh0IHN0ZXAKZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlcmlmeUVtYWlsJykuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIGZ1bmN0aW9uKGUpIHsKICBpZiAoZS5rZXkgPT09ICdFbnRlcicpIHsgZS5wcmV2ZW50RGVmYXVsdCgpOyBzZW5kQ29kZSgpOyB9Cn0pOwpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29kZUlucHV0JykuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIGZ1bmN0aW9uKGUpIHsKICBpZiAoZS5rZXkgPT09ICdFbnRlcicpIHsgZS5wcmV2ZW50RGVmYXVsdCgpOyB2ZXJpZnlDb2RlKCk7IH0KfSk7Ci8vIEF1dG8tc3VibWl0IHdoZW4gNiBkaWdpdHMgZW50ZXJlZApkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29kZUlucHV0JykuYWRkRXZlbnRMaXN0ZW5lcignaW5wdXQnLCBmdW5jdGlvbigpIHsKICBpZiAodGhpcy52YWx1ZS5sZW5ndGggPT09IDYpIHZlcmlmeUNvZGUoKTsKfSk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K").decode("utf-8")


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


FORWARD_URL_LANDING = "https://benpc.tailf7faa5.ts.net/landing"


@app.route("/landing/send-code", methods=["POST"])
def landing_send_code():
    data = request.get_json(force=True)
    try:
        resp = requests.post(FORWARD_URL_LANDING + "/send-code", json=data, timeout=10)
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/landing/verify-code", methods=["POST"])
def landing_verify_code():
    data = request.get_json(force=True)
    try:
        resp = requests.post(FORWARD_URL_LANDING + "/verify-code", json=data, timeout=10)
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({"error": str(e)}), 500




FORWARD_URL_LANDING = "https://benpc.tailf7faa5.ts.net/landing"


@app.route("/landing/send-code", methods=["POST"])
def landing_send_code():
    data = request.get_json(force=True)
    try:
        resp = requests.post(FORWARD_URL_LANDING + "/send-code", json=data, timeout=10)
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/landing/verify-code", methods=["POST"])
def landing_verify_code():
    data = request.get_json(force=True)
    try:
        resp = requests.post(FORWARD_URL_LANDING + "/verify-code", json=data, timeout=10)
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Nova BOT Multi-Channel Webhook ready!")
    print("  FB:  /webhook")
    print("  LINE: /linebot")
    print("  WA:   /whatsapp")
    app.run(host="0.0.0.0", port=10000, debug=False)
