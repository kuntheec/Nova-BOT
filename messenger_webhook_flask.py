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


LANDING_HTML = base64.b64decode("PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9InRoIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+VGhlIEdsb2JhbCBNYW5wb3dlciDigJQgSW1taWdyYXRpb24gU2VydmljZXM8L3RpdGxlPgo8c3R5bGU+CiAgKiB7IGJveC1zaXppbmc6IGJvcmRlci1ib3g7IG1hcmdpbjogMDsgcGFkZGluZzogMDsgfQogIGJvZHkgewogICAgZm9udC1mYW1pbHk6IC1hcHBsZS1zeXN0ZW0sIEJsaW5rTWFjU3lzdGVtRm9udCwgJ1NlZ29lIFVJJywgc2Fucy1zZXJpZjsKICAgIGJhY2tncm91bmQ6IGxpbmVhci1ncmFkaWVudCgxMzVkZWcsICMwZjE3MmEgMCUsICMxZTI5M2IgMTAwJSk7CiAgICBtaW4taGVpZ2h0OiAxMDB2aDsKICAgIGRpc3BsYXk6IGZsZXg7CiAgICBhbGlnbi1pdGVtczogY2VudGVyOwogICAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7CiAgICBwYWRkaW5nOiAyMHB4OwogIH0KICAuY2FyZCB7CiAgICBiYWNrZ3JvdW5kOiAjZmZmOwogICAgYm9yZGVyLXJhZGl1czogMTZweDsKICAgIHBhZGRpbmc6IDQwcHg7CiAgICBtYXgtd2lkdGg6IDUyMHB4OwogICAgd2lkdGg6IDEwMCU7CiAgICBib3gtc2hhZG93OiAwIDIwcHggNjBweCByZ2JhKDAsMCwwLDAuMyk7CiAgfQogIC5sb2dvIHsgdGV4dC1hbGlnbjogY2VudGVyOyBtYXJnaW4tYm90dG9tOiAyNHB4OyB9CiAgLmxvZ28gaDEgeyBmb250LXNpemU6IDIycHg7IGNvbG9yOiAjMWUyOTNiOyBtYXJnaW4tYm90dG9tOiA0cHg7IH0KICAubG9nbyBwIHsgZm9udC1zaXplOiAxNHB4OyBjb2xvcjogIzY0NzQ4YjsgfQoKICAvKiBDdXN0b21lciBTZWxlY3Rpb24gKi8KICAub3B0aW9uLXJvdyB7IGRpc3BsYXk6IGZsZXg7IGdhcDogMTZweDsgbWFyZ2luLWJvdHRvbTogMjRweDsgfQogIC5vcHRpb24tY2FyZCB7CiAgICBmbGV4OiAxOyBwYWRkaW5nOiAyNHB4IDE2cHg7IGJvcmRlci1yYWRpdXM6IDE0cHg7CiAgICB0ZXh0LWFsaWduOiBjZW50ZXI7IGN1cnNvcjogcG9pbnRlcjsgdHJhbnNpdGlvbjogYWxsIDAuMnM7CiAgICBib3JkZXI6IDJweCBzb2xpZCAjZTJlOGYwOwogIH0KICAub3B0aW9uLWNhcmQ6aG92ZXIgeyB0cmFuc2Zvcm06IHRyYW5zbGF0ZVkoLTJweCk7IGJveC1zaGFkb3c6IDAgNHB4IDEycHggcmdiYSgwLDAsMCwwLjEpOyB9CiAgLm9wdGlvbi1jYXJkIC5pY29uIHsgZm9udC1zaXplOiAzNnB4OyBtYXJnaW4tYm90dG9tOiA4cHg7IH0KICAub3B0aW9uLWNhcmQgLnRpdGxlIHsgZm9udC1zaXplOiAxNXB4OyBmb250LXdlaWdodDogNjAwOyB9CiAgLm9wdGlvbi1jYXJkIC5kZXNjIHsgZm9udC1zaXplOiAxMnB4OyBjb2xvcjogIzY0NzQ4YjsgbWFyZ2luLXRvcDogNHB4OyB9CiAgLm9wdGlvbi1uZXcgeyBiYWNrZ3JvdW5kOiAjZWZmNmZmOyBib3JkZXItY29sb3I6ICM5M2M1ZmQ7IH0KICAub3B0aW9uLW5ldzpob3ZlciB7IGJvcmRlci1jb2xvcjogIzNiODJmNjsgYmFja2dyb3VuZDogI2RiZWFmZTsgfQogIC5vcHRpb24tbmV3LnNlbGVjdGVkIHsgYm9yZGVyLWNvbG9yOiAjMjU2M2ViOyBiYWNrZ3JvdW5kOiAjYmZkYmZlOyB9CiAgLm9wdGlvbi1leGlzdGluZyB7IGJhY2tncm91bmQ6ICNmMGZkZjQ7IGJvcmRlci1jb2xvcjogIzg2ZWZhYzsgfQogIC5vcHRpb24tZXhpc3Rpbmc6aG92ZXIgeyBib3JkZXItY29sb3I6ICMyMmM1NWU7IGJhY2tncm91bmQ6ICNkY2ZjZTc7IH0KICAub3B0aW9uLWV4aXN0aW5nLnNlbGVjdGVkIHsgYm9yZGVyLWNvbG9yOiAjMTZhMzRhOyBiYWNrZ3JvdW5kOiAjYmJmN2QwOyB9CgogIC8qIENvbXBhbnkgQ29udGFjdCAqLwogIC5jb21wYW55LWxpbmtzIHsKICAgIGJhY2tncm91bmQ6ICNmOGZhZmM7IGJvcmRlci1yYWRpdXM6IDEycHg7IHBhZGRpbmc6IDE2cHg7CiAgICBtYXJnaW4tYm90dG9tOiAyNHB4OwogIH0KICAuY29tcGFueS1saW5rcyAubGFiZWwgeyBmb250LXNpemU6IDEycHg7IGNvbG9yOiAjNjQ3NDhiOyBtYXJnaW4tYm90dG9tOiAxMHB4OyB0ZXh0LWFsaWduOiBjZW50ZXI7IGZvbnQtd2VpZ2h0OiA1MDA7IH0KICAuY29tcGFueS1saW5rcyAubGlua3MgeyBkaXNwbGF5OiBmbGV4OyBnYXA6IDEwcHg7IGp1c3RpZnktY29udGVudDogY2VudGVyOyBmbGV4LXdyYXA6IHdyYXA7IH0KICAuY29tcGFueS1saW5rcyAubGluay1idG4gewogICAgZGlzcGxheTogaW5saW5lLWZsZXg7IGFsaWduLWl0ZW1zOiBjZW50ZXI7IGdhcDogNnB4OwogICAgcGFkZGluZzogOHB4IDE0cHg7IGJvcmRlci1yYWRpdXM6IDhweDsgZm9udC1zaXplOiAxMnB4OyBmb250LXdlaWdodDogNTAwOwogICAgdGV4dC1kZWNvcmF0aW9uOiBub25lOyB0cmFuc2l0aW9uOiBhbGwgMC4yczsKICB9CiAgLmxpbmstYnRuLWxpbmUgeyBiYWNrZ3JvdW5kOiAjZThmNWU5OyBjb2xvcjogIzA2Yzc1NTsgfQogIC5saW5rLWJ0bi1saW5lOmhvdmVyIHsgYmFja2dyb3VuZDogIzA2Yzc1NTsgY29sb3I6ICNmZmY7IH0KICAubGluay1idG4tZmIgeyBiYWNrZ3JvdW5kOiAjZTNmMmZkOyBjb2xvcjogIzE4NzdmMjsgfQogIC5saW5rLWJ0bi1mYjpob3ZlciB7IGJhY2tncm91bmQ6ICMxODc3ZjI7IGNvbG9yOiAjZmZmOyB9CiAgLmxpbmstYnRuLXdhIHsgYmFja2dyb3VuZDogI2U4ZjVlOTsgY29sb3I6ICMyNWQzNjY7IH0KICAubGluay1idG4td2E6aG92ZXIgeyBiYWNrZ3JvdW5kOiAjMjVkMzY2OyBjb2xvcjogI2ZmZjsgfQoKICAuZm9ybS1ncm91cCB7IG1hcmdpbi1ib3R0b206IDE4cHg7IH0KICBsYWJlbCB7IGRpc3BsYXk6IGJsb2NrOyBmb250LXNpemU6IDEzcHg7IGZvbnQtd2VpZ2h0OiA2MDA7IGNvbG9yOiAjMzM0MTU1OyBtYXJnaW4tYm90dG9tOiA2cHg7IH0KICBsYWJlbCAub3B0aW9uYWwgeyBmb250LXdlaWdodDogNDAwOyBjb2xvcjogIzk0YTNiODsgZm9udC1zaXplOiAxMnB4OyB9CiAgaW5wdXQsIHNlbGVjdCB7CiAgICB3aWR0aDogMTAwJTsgcGFkZGluZzogMTJweCAxNHB4OwogICAgYm9yZGVyOiAxLjVweCBzb2xpZCAjZTJlOGYwOyBib3JkZXItcmFkaXVzOiAxMHB4OwogICAgZm9udC1zaXplOiAxNXB4OyB0cmFuc2l0aW9uOiBib3JkZXItY29sb3IgMC4yczsgb3V0bGluZTogbm9uZTsKICB9CiAgaW5wdXQ6Zm9jdXMsIHNlbGVjdDpmb2N1cyB7IGJvcmRlci1jb2xvcjogIzNiODJmNjsgYm94LXNoYWRvdzogMCAwIDAgM3B4IHJnYmEoNTksMTMwLDI0NiwwLjE1KTsgfQogIC5pbnB1dC1yb3cgeyBkaXNwbGF5OiBmbGV4OyBnYXA6IDhweDsgfQogIC5pbnB1dC1yb3cgaW5wdXQgeyBmbGV4OiAxOyB9CiAgLmJ0biB7CiAgICBwYWRkaW5nOiAxMnB4IDIwcHg7IGJhY2tncm91bmQ6ICMyNTYzZWI7IGNvbG9yOiAjZmZmOwogICAgYm9yZGVyOiBub25lOyBib3JkZXItcmFkaXVzOiAxMHB4OyBmb250LXNpemU6IDE0cHg7IGZvbnQtd2VpZ2h0OiA2MDA7CiAgICBjdXJzb3I6IHBvaW50ZXI7IHRyYW5zaXRpb246IGJhY2tncm91bmQgMC4yczsgd2hpdGUtc3BhY2U6IG5vd3JhcDsKICB9CiAgLmJ0bjpob3ZlciB7IGJhY2tncm91bmQ6ICMxZDRlZDg7IH0KICAuYnRuOmRpc2FibGVkIHsgb3BhY2l0eTogMC42OyBjdXJzb3I6IG5vdC1hbGxvd2VkOyB9CiAgLmJ0bi1zbSB7IHBhZGRpbmc6IDEwcHggMTZweDsgZm9udC1zaXplOiAxM3B4OyBib3JkZXItcmFkaXVzOiA4cHg7IH0KICAuYnRuLWdyZWVuIHsgYmFja2dyb3VuZDogIzE2YTM0YTsgfQogIC5idG4tZ3JlZW46aG92ZXIgeyBiYWNrZ3JvdW5kOiAjMTU4MDNkOyB9CiAgLmJ0bi1mdWxsIHsgd2lkdGg6IDEwMCU7IHBhZGRpbmc6IDE0cHg7IGZvbnQtc2l6ZTogMTZweDsgbWFyZ2luLXRvcDogOHB4OyB9CiAgLmJ0bi1iYWNrIHsKICAgIGJhY2tncm91bmQ6IG5vbmU7IGJvcmRlcjogMXB4IHNvbGlkICNlMmU4ZjA7IGNvbG9yOiAjNjQ3NDhiOwogICAgcGFkZGluZzogOHB4IDE2cHg7IGJvcmRlci1yYWRpdXM6IDhweDsgY3Vyc29yOiBwb2ludGVyOyBmb250LXNpemU6IDEzcHg7CiAgICBtYXJnaW4tYm90dG9tOiAxNnB4OyB0cmFuc2l0aW9uOiBhbGwgMC4yczsKICB9CiAgLmJ0bi1iYWNrOmhvdmVyIHsgYmFja2dyb3VuZDogI2YxZjVmOTsgfQogIC52ZXJpZnktc3RhdHVzIHsgZGlzcGxheTogbm9uZTsgcGFkZGluZzogMTBweCAxNHB4OyBib3JkZXItcmFkaXVzOiA4cHg7IGZvbnQtc2l6ZTogMTNweDsgbWFyZ2luLXRvcDogOHB4OyB9CiAgLnZlcmlmeS1vayB7IGRpc3BsYXk6IGJsb2NrOyBiYWNrZ3JvdW5kOiAjZGNmY2U3OyBjb2xvcjogIzE2YTM0YTsgYm9yZGVyOiAxcHggc29saWQgI2JiZjdkMDsgfQogIC52ZXJpZnktZXJyIHsgZGlzcGxheTogYmxvY2s7IGJhY2tncm91bmQ6ICNmZWYyZjI7IGNvbG9yOiAjZGMyNjI2OyBib3JkZXI6IDFweCBzb2xpZCAjZmVjYWNhOyB9CiAgLnZlcmlmeS1sb2FkaW5nIHsgZGlzcGxheTogYmxvY2s7IGJhY2tncm91bmQ6ICNmOGZhZmM7IGNvbG9yOiAjNjQ3NDhiOyBib3JkZXI6IDFweCBzb2xpZCAjZTJlOGYwOyB9CiAgLnN0ZXAtaW5kaWNhdG9yIHsgZGlzcGxheTogZmxleDsgZ2FwOiA4cHg7IG1hcmdpbi1ib3R0b206IDI0cHg7IGp1c3RpZnktY29udGVudDogY2VudGVyOyB9CiAgLnN0ZXAgeyB3aWR0aDogMzJweDsgaGVpZ2h0OiAzMnB4OyBib3JkZXItcmFkaXVzOiA1MCU7IGRpc3BsYXk6IGZsZXg7IGFsaWduLWl0ZW1zOiBjZW50ZXI7IGp1c3RpZnktY29udGVudDogY2VudGVyOyBmb250LXNpemU6IDEzcHg7IGZvbnQtd2VpZ2h0OiA2MDA7IH0KICAuc3RlcC1hY3RpdmUgeyBiYWNrZ3JvdW5kOiAjMjU2M2ViOyBjb2xvcjogI2ZmZjsgfQogIC5zdGVwLWRvbmUgeyBiYWNrZ3JvdW5kOiAjMTZhMzRhOyBjb2xvcjogI2ZmZjsgfQogIC5zdGVwLXBlbmRpbmcgeyBiYWNrZ3JvdW5kOiAjZTJlOGYwOyBjb2xvcjogIzk0YTNiODsgfQogIC5zdGVwLWxpbmUgeyB3aWR0aDogNDBweDsgaGVpZ2h0OiAycHg7IGFsaWduLXNlbGY6IGNlbnRlcjsgYmFja2dyb3VuZDogI2UyZThmMDsgfQogIC5zdGVwLWxpbmUtZG9uZSB7IGJhY2tncm91bmQ6ICMxNmEzNGE7IH0KICAubm90ZSB7IGZvbnQtc2l6ZTogMTJweDsgY29sb3I6ICM2NDc0OGI7IHRleHQtYWxpZ246IGNlbnRlcjsgbWFyZ2luLXRvcDogMjBweDsgbGluZS1oZWlnaHQ6IDEuNTsgfQogIC5zdWNjZXNzIHsgZGlzcGxheTogbm9uZTsgdGV4dC1hbGlnbjogY2VudGVyOyBwYWRkaW5nOiAzMHB4IDA7IH0KICAuc3VjY2VzcyAuY2hlY2sgeyBmb250LXNpemU6IDQ4cHg7IG1hcmdpbi1ib3R0b206IDEycHg7IH0KICAuc3VjY2VzcyBoMiB7IGNvbG9yOiAjMTZhMzRhOyBtYXJnaW4tYm90dG9tOiA4cHg7IH0KICAuc3VjY2VzcyBwIHsgY29sb3I6ICM2NDc0OGI7IGZvbnQtc2l6ZTogMTRweDsgbGluZS1oZWlnaHQ6IDEuNjsgfQogIC5lcnJvci1tc2cgeyBkaXNwbGF5OiBub25lOyBjb2xvcjogI2RjMjYyNjsgZm9udC1zaXplOiAxM3B4OyBtYXJnaW4tdG9wOiAxMHB4OyB0ZXh0LWFsaWduOiBjZW50ZXI7IH0KCiAgLnJldHJpZXZlZC1kYXRhIHsKICAgIGJhY2tncm91bmQ6ICNmOGZhZmM7IGJvcmRlci1yYWRpdXM6IDEwcHg7IHBhZGRpbmc6IDE2cHg7CiAgICBtYXJnaW4tYm90dG9tOiAxOHB4OyBkaXNwbGF5OiBub25lOwogIH0KICAucmV0cmlldmVkLWRhdGEgLnJkLWxhYmVsIHsgZm9udC1zaXplOiAxMnB4OyBjb2xvcjogIzI1NjNlYjsgZm9udC13ZWlnaHQ6IDYwMDsgbWFyZ2luLWJvdHRvbTogOHB4OyB9CiAgLnJldHJpZXZlZC1kYXRhIC5yZC1yb3cgeyBmb250LXNpemU6IDEzcHg7IGNvbG9yOiAjMzM0MTU1OyBsaW5lLWhlaWdodDogMS44OyB9CiAgLnJldHJpZXZlZC1kYXRhIC5yZC1yb3cgc3BhbiB7IGNvbG9yOiAjNjQ3NDhiOyB9CiAgLnJldHJpZXZlZC1kYXRhIC5yZC1lZGl0LWhpbnQgewogICAgZm9udC1zaXplOiAxMnB4OyBjb2xvcjogIzE2YTM0YTsgbWFyZ2luLXRvcDogOHB4OwogICAgcGFkZGluZy10b3A6IDhweDsgYm9yZGVyLXRvcDogMXB4IHNvbGlkICNlMmU4ZjA7CiAgfQo8L3N0eWxlPgo8L2hlYWQ+Cjxib2R5PgoKPGRpdiBjbGFzcz0iY2FyZCIgaWQ9ImZvcm1DYXJkIj4KICA8ZGl2IGNsYXNzPSJsb2dvIj4KICAgIDxoMT5UaGUgR2xvYmFsIE1hbnBvd2VyPC9oMT4KICAgIDxwPkltbWlncmF0aW9uIENvbnN1bHRhdGlvbiDigJQg4Lil4LiH4LiX4Liw4LmA4Lia4Li14Lii4LiZ4Lij4Lix4Lia4LiE4Liz4Lib4Lij4Li24LiB4Lip4LiyPC9wPgogIDwvZGl2PgoKICA8IS0tIENvbXBhbnkgQ29udGFjdCBJbmZvIC0tPgogIDxkaXYgY2xhc3M9ImNvbXBhbnktbGlua3MiPgogICAgPGRpdiBjbGFzcz0ibGFiZWwiPuC4leC4tOC4lOC4leC5iOC4reC5gOC4o+C4suC4nOC5iOC4suC4meC4iuC5iOC4reC4h+C4l+C4suC4h+C4reC4t+C5iOC4meC5hOC4lOC5ieC4l+C4seC4meC4l+C4tTwvZGl2PgogICAgPGRpdiBjbGFzcz0ibGlua3MiPgogICAgICA8YSBocmVmPSJodHRwczovL2xpbmUubWUvdGkvcC9+QHRoZWdsb2JhbG1hbnBvd2VyIiB0YXJnZXQ9Il9ibGFuayIgY2xhc3M9ImxpbmstYnRuIGxpbmstYnRuLWxpbmUiPvCfkpogTElORTogQHRoZWdsb2JhbG1hbnBvd2VyPC9hPgogICAgICA8YSBocmVmPSJodHRwczovL20ubWUvVGhlR2xvYmFsTWFucG93ZXIiIHRhcmdldD0iX2JsYW5rIiBjbGFzcz0ibGluay1idG4gbGluay1idG4tZmIiPvCfkqwgRkI6IFRoZSBHbG9iYWwgTWFucG93ZXI8L2E+CiAgICAgIDxhIGhyZWY9Imh0dHBzOi8vd2EubWUvNjQyMTIzNDU2NzgiIHRhcmdldD0iX2JsYW5rIiBjbGFzcz0ibGluay1idG4gbGluay1idG4td2EiPvCfk7EgV2hhdHNBcHA6IDAyMSAyMzQgNTY3ODwvYT4KICAgIDwvZGl2PgogIDwvZGl2PgoKICA8IS0tIEN1c3RvbWVyIFR5cGUgU2VsZWN0aW9uIC0tPgogIDxkaXYgY2xhc3M9Im9wdGlvbi1yb3ciIGlkPSJ0eXBlU2VsZWN0aW9uIj4KICAgIDxkaXYgY2xhc3M9Im9wdGlvbi1jYXJkIG9wdGlvbi1uZXciIG9uY2xpY2s9InNlbGVjdFR5cGUoJ25ldycpIj4KICAgICAgPGRpdiBjbGFzcz0iaWNvbiI+8J+GlTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ0aXRsZSI+TmV3IEN1c3RvbWVyPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImRlc2MiPuC4peC4h+C4l+C4sOC5gOC4muC4teC4ouC4meC4hOC4o+C4seC5ieC4h+C5geC4o+C4gTwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJvcHRpb24tY2FyZCBvcHRpb24tZXhpc3RpbmciIG9uY2xpY2s9InNlbGVjdFR5cGUoJ2V4aXN0aW5nJykiPgogICAgICA8ZGl2IGNsYXNzPSJpY29uIj7wn5SEPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InRpdGxlIj5FeGlzdGluZyBDdXN0b21lcjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJkZXNjIj7guYDguITguKLguKXguIfguJfguLDguYDguJrguLXguKLguJnguYHguKXguYnguKc8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgoKICA8ZGl2IGlkPSJ2ZXJpZnlTZWN0aW9uIiBzdHlsZT0iZGlzcGxheTpub25lOyI+CiAgICA8YnV0dG9uIGNsYXNzPSJidG4tYmFjayIgb25jbGljaz0iYmFja1RvVHlwZSgpIj7ihpAg4LiB4Lil4Lix4LiaPC9idXR0b24+CgogICAgPCEtLSBTdGVwIEluZGljYXRvciAtLT4KICAgIDxkaXYgY2xhc3M9InN0ZXAtaW5kaWNhdG9yIj4KICAgICAgPGRpdiBjbGFzcz0ic3RlcCBzdGVwLWFjdGl2ZSIgaWQ9InN0ZXAxIj4xPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InN0ZXAtbGluZSIgaWQ9ImxpbmUxIj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3RlcCBzdGVwLXBlbmRpbmciIGlkPSJzdGVwMiI+MjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzdGVwLWxpbmUiIGlkPSJsaW5lMiI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InN0ZXAgc3RlcC1wZW5kaW5nIiBpZD0ic3RlcDMiPjM8L2Rpdj4KICAgIDwvZGl2PgoKICAgIDxkaXYgaWQ9ImVycm9yVG9wIiBjbGFzcz0iZXJyb3ItbXNnIj48L2Rpdj4KCiAgICA8IS0tIFNURVAgMTogRW1haWwgVmVyaWZpY2F0aW9uIC0tPgogICAgPGRpdiBpZD0ic3RlcDFDb250ZW50Ij4KICAgICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgICAgPGxhYmVsPuC4reC4teC5gOC4oeC4pSA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPio8L3NwYW4+PC9sYWJlbD4KICAgICAgICA8ZGl2IGNsYXNzPSJpbnB1dC1yb3ciPgogICAgICAgICAgPGlucHV0IHR5cGU9ImVtYWlsIiBpZD0idmVyaWZ5RW1haWwiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPSJ5b3VyQGVtYWlsLmNvbSI+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gYnRuLXNtIiBpZD0ic2VuZENvZGVCdG4iIG9uY2xpY2s9InNlbmRDb2RlKCkiPuC4quC5iOC4h+C4o+C4q+C4seC4qjwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBpZD0idmVyaWZ5U3RhdHVzIiBjbGFzcz0idmVyaWZ5LXN0YXR1cyI+PC9kaXY+CgogICAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIiBzdHlsZT0iZGlzcGxheTpub25lOyIgaWQ9ImNvZGVHcm91cCI+CiAgICAgICAgPGxhYmVsPuC4o+C4q+C4seC4quC4ouC4t+C4meC4ouC4seC4mSA2IOC4q+C4peC4seC4gTwvbGFiZWw+CiAgICAgICAgPGRpdiBjbGFzcz0iaW5wdXQtcm93Ij4KICAgICAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBpZD0iY29kZUlucHV0IiBtYXhsZW5ndGg9IjYiIHBsYWNlaG9sZGVyPSIwMDAwMDAiIGlucHV0bW9kZT0ibnVtZXJpYyIgcGF0dGVybj0iWzAtOV0qIj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBidG4tc20gYnRuLWdyZWVuIiBpZD0idmVyaWZ5Q29kZUJ0biIgb25jbGljaz0idmVyaWZ5Q29kZSgpIj7guKLguLfguJnguKLguLHguJk8L2J1dHRvbj4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KCiAgICA8IS0tIFNURVAgMjogRm9ybSAtLT4KICAgIDxkaXYgaWQ9InN0ZXAyQ29udGVudCIgc3R5bGU9ImRpc3BsYXk6bm9uZTsiPgogICAgICA8ZGl2IGNsYXNzPSJjaGFubmVscy1oaW50IiBpZD0idmVyaWZ5U3VjY2Vzc01zZyI+CiAgICAgICAg4pyFIOC4ouC4t+C4meC4ouC4seC4meC4reC4teC5gOC4oeC4peC5gOC4o+C4teC4ouC4muC4o+C5ieC4reC4ouC5geC4peC5ieC4pzxicj4KICAgICAgICA8c3Ryb25nPvCfk50g4LiW4LmJ4Liy4Lil4LiH4LiX4Liw4LmA4Lia4Li14Lii4LiZ4LmB4Lil4LmJ4LinIOKAlCDguIHguKPguK3guIHguK3guLXguYDguKHguKXguYDguJTguLTguKEg4Lij4Liw4Lia4Lia4LiI4Liw4Lit4Lix4Lib4LmA4LiU4LiV4LiC4LmJ4Lit4Lih4Li54Lil4LmD4Lir4LmJ4Lit4Lix4LiV4LmC4LiZ4Lih4Lix4LiV4Li0PC9zdHJvbmc+CiAgICAgIDwvZGl2PgoKICAgICAgPCEtLSBSZXRyaWV2ZWQgZXhpc3RpbmcgZGF0YSAtLT4KICAgICAgPGRpdiBjbGFzcz0icmV0cmlldmVkLWRhdGEiIGlkPSJyZXRyaWV2ZWREYXRhIj4KICAgICAgICA8ZGl2IGNsYXNzPSJyZC1sYWJlbCI+8J+TiyDguILguYnguK3guKHguLnguKXguYDguJTguLTguKHguILguK3guIfguITguLjguJM8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJyZC1yb3ciIGlkPSJyZENvbnRlbnQiPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9InJkLWVkaXQtaGludCI+4pyP77iPIOC5geC4geC5ieC5hOC4guC4guC5ieC4reC4oeC4ueC4peC4lOC5ieC4suC4meC4peC5iOC4suC4hyDguYHguKXguYnguKfguIHguJTguKrguYjguIfguYDguJ7guLfguYjguK3guK3guLHguJvguYDguJTguJU8L2Rpdj4KICAgICAgPC9kaXY+CgogICAgICA8Zm9ybSBpZD0ibGVhZEZvcm0iPgogICAgICAgIDxpbnB1dCB0eXBlPSJoaWRkZW4iIG5hbWU9ImVtYWlsIiBpZD0iaGlkZGVuRW1haWwiIHZhbHVlPSIiPgogICAgICAgIDxpbnB1dCB0eXBlPSJoaWRkZW4iIG5hbWU9ImN1c3RvbWVyX3R5cGUiIGlkPSJjdXN0b21lclR5cGUiIHZhbHVlPSJuZXciPgoKICAgICAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgICAgIDxsYWJlbD7guIrguLfguYjguK0t4LiZ4Liy4Lih4Liq4LiB4Li44LilIDxzcGFuIGNsYXNzPSJvcHRpb25hbCI+Kjwvc3Bhbj48L2xhYmVsPgogICAgICAgICAgPGlucHV0IHR5cGU9InRleHQiIG5hbWU9Im5hbWUiIGlkPSJmaWVsZE5hbWUiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPSLguYDguIrguYjguJkg4Liq4Lih4LiK4Liy4LiiIOC5g+C4iOC4lOC4tSI+CiAgICAgICAgPC9kaXY+CgogICAgICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPgogICAgICAgICAgPGxhYmVsPuC5gOC4muC4reC4o+C5jOC5guC4l+C4o+C4qOC4seC4nuC4l+C5jCA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPio8L3NwYW4+PC9sYWJlbD4KICAgICAgICAgIDxpbnB1dCB0eXBlPSJ0ZWwiIG5hbWU9InBob25lIiBpZD0iZmllbGRQaG9uZSIgcmVxdWlyZWQgcGxhY2Vob2xkZXI9IuC5gOC4iuC5iOC4mSAwMjEyMzQ1Njc4Ij4KICAgICAgICA8L2Rpdj4KCiAgICAgICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgICAgICA8bGFiZWw+TElORSBJRCA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPihvcHRpb25hbCk8L3NwYW4+PC9sYWJlbD4KICAgICAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBuYW1lPSJsaW5lX2lkIiBpZD0iZmllbGRMaW5lIiBwbGFjZWhvbGRlcj0iTElORSBJRCDguKvguKPguLfguK3guYDguJrguK3guKPguYzguJfguLXguYjguKXguIfguJfguLDguYDguJrguLXguKLguJkgTElORSI+CiAgICAgICAgPC9kaXY+CgogICAgICAgIDxkaXYgY2xhc3M9ImZvcm0tZ3JvdXAiPgogICAgICAgICAgPGxhYmVsPkZhY2Vib29rIE1lc3NlbmdlciA8c3BhbiBjbGFzcz0ib3B0aW9uYWwiPihvcHRpb25hbCk8L3NwYW4+PC9sYWJlbD4KICAgICAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBuYW1lPSJtZXNzZW5nZXJfaWQiIGlkPSJmaWVsZEZiIiBwbGFjZWhvbGRlcj0i4LiK4Li34LmI4Lit4Lia4Lix4LiN4LiK4Li1IEZhY2Vib29rIj4KICAgICAgICA8L2Rpdj4KCiAgICAgICAgPGRpdiBjbGFzcz0iZm9ybS1ncm91cCI+CiAgICAgICAgICA8bGFiZWw+V2hhdHNBcHAgPHNwYW4gY2xhc3M9Im9wdGlvbmFsIj4ob3B0aW9uYWwpPC9zcGFuPjwvbGFiZWw+CiAgICAgICAgICA8aW5wdXQgdHlwZT0idGVsIiBuYW1lPSJ3aGF0c2FwcCIgaWQ9ImZpZWxkV2EiIHBsYWNlaG9sZGVyPSLguYDguJrguK3guKPguYwgV2hhdHNBcHAgKOC4o+C4p+C4oeC4o+C4q+C4seC4quC4m+C4o+C4sOC5gOC4l+C4qCkiPgogICAgICAgIDwvZGl2PgoKICAgICAgICA8ZGl2IGNsYXNzPSJmb3JtLWdyb3VwIj4KICAgICAgICAgIDxsYWJlbD7guKvguLHguKfguILguYnguK3guJfguLXguYjguJXguYnguK3guIfguIHguLLguKPguJvguKPguLbguIHguKnguLI8L2xhYmVsPgogICAgICAgICAgPHNlbGVjdCBuYW1lPSJ0b3BpYyIgaWQ9ImZpZWxkVG9waWMiPgogICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJ2aXNhIj7guILguK0gVmlzYSAvIOC4leC5iOC4rSBWaXNhPC9vcHRpb24+CiAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9InJlc2lkZW5jeSI+4LiW4Li04LmI4LiZ4LiX4Li14LmI4Lit4Lii4Li54LmIIChSZXNpZGVuY3kpPC9vcHRpb24+CiAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9IndvcmsiPuC5g+C4muC4reC4meC4uOC4jeC4suC4leC4l+C4s+C4h+C4suC4mTwvb3B0aW9uPgogICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJmYW1pbHkiPkZhbWlseSAvIFBhcnRuZXIgVmlzYTwvb3B0aW9uPgogICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJvdGhlciI+4Lit4Li34LmI4LiZ4LmGPC9vcHRpb24+CiAgICAgICAgICA8L3NlbGVjdD4KICAgICAgICA8L2Rpdj4KCiAgICAgICAgPGJ1dHRvbiB0eXBlPSJzdWJtaXQiIGNsYXNzPSJidG4gYnRuLWZ1bGwiIGlkPSJzdWJtaXRCdG4iPuC4quC5iOC4h+C4guC5ieC4reC4oeC4ueC4pTwvYnV0dG9uPgogICAgICAgIDxkaXYgY2xhc3M9ImVycm9yLW1zZyIgaWQ9ImZvcm1FcnJvciI+PC9kaXY+CiAgICAgIDwvZm9ybT4KICAgIDwvZGl2PgoKICAgIDxkaXYgY2xhc3M9Im5vdGUiPgogICAgICDguILguYnguK3guKHguLnguKXguILguK3guIfguITguLjguJPguIjguLDguJbguLnguIHguYDguIHguYfguJrguYDguJvguYfguJnguITguKfguLLguKHguKXguLHguJrguYHguKXguLDguYPguIrguYnguKrguLPguKvguKPguLHguJrguIHguLLguKPguYPguKvguYnguITguLPguJvguKPguLbguIHguKnguLLguYDguJfguYjguLLguJnguLHguYnguJkKICAgIDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0gU3VjY2VzcyBTY3JlZW4gLS0+CjxkaXYgY2xhc3M9ImNhcmQiIGlkPSJzdWNjZXNzQ2FyZCIgc3R5bGU9ImRpc3BsYXk6bm9uZTsiPgogIDxkaXYgY2xhc3M9InN1Y2Nlc3MiIHN0eWxlPSJkaXNwbGF5OmJsb2NrOyI+CiAgICA8ZGl2IGNsYXNzPSJjaGVjayI+4pyFPC9kaXY+CiAgICA8aDI+UmVjZWl2ZWQhPC9oMj4KICAgIDxwPldlIGhhdmUgcmVjZWl2ZWQgeW91ciBpbmZvcm1hdGlvbiBhbmQgd2lsbCBnZXQgYmFjayB0byB5b3Ugc29vbmVzdC48YnI+VGhhbmsgeW91IGZvciBjaG9vc2luZyBUaGUgR2xvYmFsIE1hbnBvd2VyPC9wPgogIDwvZGl2Pgo8L2Rpdj4KCjxzY3JpcHQ+CmxldCB2ZXJpZmllZEVtYWlsID0gJyc7CmxldCBjdXN0b21lclR5cGUgPSAnbmV3JzsKCmZ1bmN0aW9uIHNlbGVjdFR5cGUodHlwZSkgewogIGN1c3RvbWVyVHlwZSA9IHR5cGU7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2N1c3RvbWVyVHlwZScpLnZhbHVlID0gdHlwZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndHlwZVNlbGVjdGlvbicpLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlcmlmeVNlY3Rpb24nKS5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKfQoKZnVuY3Rpb24gYmFja1RvVHlwZSgpIHsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5U2VjdGlvbicpLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3R5cGVTZWxlY3Rpb24nKS5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGVwMUNvbnRlbnQnKS5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RlcDJDb250ZW50Jykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29kZUdyb3VwJykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5U3RhdHVzJykuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMnOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlTdGF0dXMnKS50ZXh0Q29udGVudCA9ICcnOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlFbWFpbCcpLnJlYWRPbmx5ID0gZmFsc2U7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0ZXAxJykuY2xhc3NOYW1lID0gJ3N0ZXAgc3RlcC1hY3RpdmUnOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaW5lMScpLmNsYXNzTmFtZSA9ICdzdGVwLWxpbmUnOwp9Cgphc3luYyBmdW5jdGlvbiBzZW5kQ29kZSgpIHsKICBjb25zdCBlbWFpbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlFbWFpbCcpLnZhbHVlLnRyaW0oKTsKICBjb25zdCBidG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZENvZGVCdG4nKTsKICBjb25zdCBzdGF0dXMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5U3RhdHVzJyk7CgogIGlmICghZW1haWwgfHwgIWVtYWlsLmluY2x1ZGVzKCdAJykpIHsKICAgIHN0YXR1cy5jbGFzc05hbWUgPSAndmVyaWZ5LXN0YXR1cyB2ZXJpZnktZXJyJzsKICAgIHN0YXR1cy50ZXh0Q29udGVudCA9ICfguIHguKPguLjguJPguLLguIHguKPguK3guIHguK3guLXguYDguKHguKXguJfguLXguYjguJbguLnguIHguJXguYnguK3guIcnOwogICAgcmV0dXJuOwogIH0KCiAgYnRuLmRpc2FibGVkID0gdHJ1ZTsKICBidG4udGV4dENvbnRlbnQgPSAn4LiB4Liz4Lil4Lix4LiH4Liq4LmI4LiHLi4uJzsKICBzdGF0dXMuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMgdmVyaWZ5LWxvYWRpbmcnOwogIHN0YXR1cy50ZXh0Q29udGVudCA9ICfguIHguLPguKXguLHguIfguKrguYjguIfguKPguKvguLHguKrguKLguLfguJnguKLguLHguJnguYTguJvguKLguLHguIfguK3guLXguYDguKHguKUuLi4nOwoKICB0cnkgewogICAgY29uc3QgcmVzID0gYXdhaXQgZmV0Y2goJy9sYW5kaW5nL3NlbmQtY29kZScsIHsKICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgIGhlYWRlcnM6IHsgJ0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJyB9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7IGVtYWlsIH0pCiAgICB9KTsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXMuanNvbigpOwoKICAgIGlmIChyZXMub2spIHsKICAgICAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1vayc7CiAgICAgIHN0YXR1cy50ZXh0Q29udGVudCA9ICfinIUg4Liq4LmI4LiH4Lij4Lir4Lix4Liq4LmE4Lib4Lii4Lix4LiH4Lit4Li14LmA4Lih4Lil4LiC4Lit4LiH4LiE4Li44LiT4LmB4Lil4LmJ4LinIOC4geC4o+C4uOC4k+C4suC4leC4o+C4p+C4iOC4quC4reC4muC4reC4teC5gOC4oeC4pSc7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb2RlR3JvdXAnKS5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlcmlmeUVtYWlsJykucmVhZE9ubHkgPSB0cnVlOwogICAgICBidG4udGV4dENvbnRlbnQgPSAn4Liq4LmI4LiH4Lit4Li14LiB4LiE4Lij4Lix4LmJ4LiHJzsKICAgICAgYnRuLmRpc2FibGVkID0gZmFsc2U7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb2RlSW5wdXQnKS5mb2N1cygpOwogICAgfSBlbHNlIHsKICAgICAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1lcnInOwogICAgICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4p2MICcgKyAoZGF0YS5lcnJvciB8fCAn4Liq4LmI4LiH4Lij4Lir4Lix4Liq4LmE4Lih4LmI4Liq4Liz4LmA4Lij4LmH4LiIJyk7CiAgICAgIGJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgICBidG4udGV4dENvbnRlbnQgPSAn4Liq4LmI4LiH4Lij4Lir4Lix4LiqJzsKICAgIH0KICB9IGNhdGNoIChlcnIpIHsKICAgIHN0YXR1cy5jbGFzc05hbWUgPSAndmVyaWZ5LXN0YXR1cyB2ZXJpZnktZXJyJzsKICAgIHN0YXR1cy50ZXh0Q29udGVudCA9ICfinYwg4LmA4LiB4Li04LiU4LiC4LmJ4Lit4Lic4Li04LiU4Lie4Lil4Liy4LiUIOC4geC4o+C4uOC4k+C4suC4peC4reC4h+C5g+C4q+C4oeC5iCc7CiAgICBidG4uZGlzYWJsZWQgPSBmYWxzZTsKICAgIGJ0bi50ZXh0Q29udGVudCA9ICfguKrguYjguIfguKPguKvguLHguKonOwogIH0KfQoKYXN5bmMgZnVuY3Rpb24gdmVyaWZ5Q29kZSgpIHsKICBjb25zdCBlbWFpbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlFbWFpbCcpLnZhbHVlLnRyaW0oKTsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvZGVJbnB1dCcpLnZhbHVlLnRyaW0oKTsKICBjb25zdCBidG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVyaWZ5Q29kZUJ0bicpOwogIGNvbnN0IHN0YXR1cyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlTdGF0dXMnKTsKCiAgaWYgKCFjb2RlIHx8IGNvZGUubGVuZ3RoICE9PSA2KSB7CiAgICBzdGF0dXMuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMgdmVyaWZ5LWVycic7CiAgICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4LiB4Lij4Li44LiT4Liy4LiB4Lij4Lit4LiB4Lij4Lir4Lix4Liq4Lii4Li34LiZ4Lii4Lix4LiZIDYg4Lir4Lil4Lix4LiBJzsKICAgIHJldHVybjsKICB9CgogIGJ0bi5kaXNhYmxlZCA9IHRydWU7CiAgYnRuLnRleHRDb250ZW50ID0gJ+C4geC4s+C4peC4seC4h+C4leC4o+C4p+C4iOC4quC4reC4mi4uLic7CiAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1sb2FkaW5nJzsKICBzdGF0dXMudGV4dENvbnRlbnQgPSAn4LiB4Liz4Lil4Lix4LiH4LiV4Lij4Lin4LiI4Liq4Lit4Lia4Lij4Lir4Lix4LiqLi4uJzsKCiAgdHJ5IHsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvbGFuZGluZy92ZXJpZnktY29kZScsIHsKICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgIGhlYWRlcnM6IHsgJ0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJyB9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7IGVtYWlsLCBjb2RlIH0pCiAgICB9KTsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXMuanNvbigpOwoKICAgIGlmIChyZXMub2spIHsKICAgICAgdmVyaWZpZWRFbWFpbCA9IGVtYWlsOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnaGlkZGVuRW1haWwnKS52YWx1ZSA9IGVtYWlsOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RlcDEnKS5jbGFzc05hbWUgPSAnc3RlcCBzdGVwLWRvbmUnOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RlcDEnKS50ZXh0Q29udGVudCA9ICfinJMnOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbGluZTEnKS5jbGFzc05hbWUgPSAnc3RlcC1saW5lIHN0ZXAtbGluZS1kb25lJzsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0ZXAyJykuY2xhc3NOYW1lID0gJ3N0ZXAgc3RlcC1hY3RpdmUnOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RlcDInKS50ZXh0Q29udGVudCA9ICcyJzsKCiAgICAgIC8vIElmIGV4aXN0aW5nIGN1c3RvbWVyLCByZXRyaWV2ZSB0aGVpciBkYXRhCiAgICAgIGlmIChjdXN0b21lclR5cGUgPT09ICdleGlzdGluZycpIHsKICAgICAgICBhd2FpdCByZXRyaWV2ZUV4aXN0aW5nRGF0YShlbWFpbCk7CiAgICAgIH0KCiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGVwMUNvbnRlbnQnKS5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RlcDJDb250ZW50Jykuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICB9IGVsc2UgewogICAgICBzdGF0dXMuY2xhc3NOYW1lID0gJ3ZlcmlmeS1zdGF0dXMgdmVyaWZ5LWVycic7CiAgICAgIHN0YXR1cy50ZXh0Q29udGVudCA9ICfinYwgJyArIChkYXRhLmVycm9yIHx8ICfguKPguKvguLHguKrguYTguKHguYjguJbguLnguIHguJXguYnguK3guIcnKTsKICAgICAgYnRuLmRpc2FibGVkID0gZmFsc2U7CiAgICAgIGJ0bi50ZXh0Q29udGVudCA9ICfguKLguLfguJnguKLguLHguJknOwogICAgfQogIH0gY2F0Y2ggKGVycikgewogICAgc3RhdHVzLmNsYXNzTmFtZSA9ICd2ZXJpZnktc3RhdHVzIHZlcmlmeS1lcnInOwogICAgc3RhdHVzLnRleHRDb250ZW50ID0gJ+KdjCDguYDguIHguLTguJTguILguYnguK3guJzguLTguJTguJ7guKXguLLguJQg4LiB4Lij4Li44LiT4Liy4Lil4Lit4LiH4LmD4Lir4Lih4LmIJzsKICAgIGJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgYnRuLnRleHRDb250ZW50ID0gJ+C4ouC4t+C4meC4ouC4seC4mSc7CiAgfQp9Cgphc3luYyBmdW5jdGlvbiByZXRyaWV2ZUV4aXN0aW5nRGF0YShlbWFpbCkgewogIHRyeSB7CiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2xhbmRpbmcvZ2V0LWN1c3RvbWVyJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeyAnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nIH0sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsgZW1haWwgfSkKICAgIH0pOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlcy5qc29uKCk7CgogICAgaWYgKHJlcy5vayAmJiBkYXRhLmZvdW5kKSB7CiAgICAgIC8vIFNob3cgcmV0cmlldmVkIGRhdGEKICAgICAgY29uc3QgcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmV0cmlldmVkRGF0YScpOwogICAgICBjb25zdCByYyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZENvbnRlbnQnKTsKICAgICAgcmMuaW5uZXJIVE1MID0gJyc7CiAgICAgIGlmIChkYXRhLmRhdGEubmFtZSkgcmMuaW5uZXJIVE1MICs9ICc8c3Bhbj7guIrguLfguYjguK06PC9zcGFuPiAnICsgZGF0YS5kYXRhLm5hbWUgKyAnPGJyPic7CiAgICAgIGlmIChkYXRhLmRhdGEucGhvbmUpIHJjLmlubmVySFRNTCArPSAnPHNwYW4+4LmA4Lia4Lit4Lij4LmMOjwvc3Bhbj4gJyArIGRhdGEuZGF0YS5waG9uZSArICc8YnI+JzsKICAgICAgaWYgKGRhdGEuZGF0YS5saW5lX2lkKSByYy5pbm5lckhUTUwgKz0gJzxzcGFuPkxJTkU6PC9zcGFuPiAnICsgZGF0YS5kYXRhLmxpbmVfaWQgKyAnPGJyPic7CiAgICAgIGlmIChkYXRhLmRhdGEubWVzc2VuZ2VyX2lkKSByYy5pbm5lckhUTUwgKz0gJzxzcGFuPkZCOjwvc3Bhbj4gJyArIGRhdGEuZGF0YS5tZXNzZW5nZXJfaWQgKyAnPGJyPic7CiAgICAgIGlmIChkYXRhLmRhdGEud2hhdHNhcHApIHJjLmlubmVySFRNTCArPSAnPHNwYW4+V0E6PC9zcGFuPiAnICsgZGF0YS5kYXRhLndoYXRzYXBwICsgJzxicj4nOwogICAgICByZC5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKCiAgICAgIC8vIFByZS1maWxsIGZvcm0KICAgICAgaWYgKGRhdGEuZGF0YS5uYW1lKSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmllbGROYW1lJykudmFsdWUgPSBkYXRhLmRhdGEubmFtZTsKICAgICAgaWYgKGRhdGEuZGF0YS5waG9uZSkgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ZpZWxkUGhvbmUnKS52YWx1ZSA9IGRhdGEuZGF0YS5waG9uZTsKICAgICAgaWYgKGRhdGEuZGF0YS5saW5lX2lkKSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmllbGRMaW5lJykudmFsdWUgPSBkYXRhLmRhdGEubGluZV9pZDsKICAgICAgaWYgKGRhdGEuZGF0YS5tZXNzZW5nZXJfaWQpIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmaWVsZEZiJykudmFsdWUgPSBkYXRhLmRhdGEubWVzc2VuZ2VyX2lkOwogICAgICBpZiAoZGF0YS5kYXRhLndoYXRzYXBwKSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmllbGRXYScpLnZhbHVlID0gZGF0YS5kYXRhLndoYXRzYXBwOwogICAgICBpZiAoZGF0YS5kYXRhLnRvcGljKSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmllbGRUb3BpYycpLnZhbHVlID0gZGF0YS5kYXRhLnRvcGljOwogICAgfSBlbHNlIHsKICAgICAgLy8gTm90IGZvdW5kIGFzIGV4aXN0aW5nIC0gc2hvdyBhcyBuZXcgY3VzdG9tZXIKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlcmlmeVN1Y2Nlc3NNc2cnKS5pbm5lckhUTUwgPSAn4pyFIOC4ouC4t+C4meC4ouC4seC4meC4reC4teC5gOC4oeC4peC5gOC4o+C4teC4ouC4muC4o+C5ieC4reC4ouC5geC4peC5ieC4pzxicj48c3BhbiBzdHlsZT0iY29sb3I6IzI1NjNlYjsiPuC5hOC4oeC5iOC4nuC4muC4guC5ieC4reC4oeC4ueC4peC5gOC4lOC4tOC4oeC4guC4reC4h+C4hOC4uOC4kyDguIHguKPguLjguJPguLLguIHguKPguK3guIHguILguYnguK3guKHguLnguKXguJTguYnguLLguJnguKXguYjguLLguIc8L3NwYW4+JzsKICAgIH0KICB9IGNhdGNoIChlcnIpIHsKICAgIC8vIFNpbGVudGx5IGZhaWwgLSBqdXN0IHNob3cgZm9ybQogIH0KfQoKZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2xlYWRGb3JtJykuYWRkRXZlbnRMaXN0ZW5lcignc3VibWl0JywgYXN5bmMgZnVuY3Rpb24oZSkgewogIGUucHJldmVudERlZmF1bHQoKTsKICBjb25zdCBidG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3VibWl0QnRuJyk7CiAgY29uc3QgZXJyRWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZm9ybUVycm9yJyk7CiAgYnRuLmRpc2FibGVkID0gdHJ1ZTsKICBidG4udGV4dENvbnRlbnQgPSAn4LiB4Liz4Lil4Lix4LiH4Liq4LmI4LiHLi4uJzsKICBlcnJFbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwoKICBjb25zdCBmb3JtRGF0YSA9IG5ldyBGb3JtRGF0YSh0aGlzKTsKICBjb25zdCBkYXRhID0gT2JqZWN0LmZyb21FbnRyaWVzKGZvcm1EYXRhLmVudHJpZXMoKSk7CiAgZGF0YS5lbWFpbCA9IHZlcmlmaWVkRW1haWw7CgogIHRyeSB7CiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2xhbmRpbmcvc3VibWl0JywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeyAnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nIH0sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KGRhdGEpCiAgICB9KTsKCiAgICBpZiAoIXJlcy5vaykgdGhyb3cgbmV3IEVycm9yKCfguKrguYjguIfguILguYnguK3guKHguLnguKXguYTguKHguYjguKrguLPguYDguKPguYfguIgnKTsKCiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZm9ybUNhcmQnKS5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N1Y2Nlc3NDYXJkJykuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgfSBjYXRjaCAoZXJyKSB7CiAgICBlcnJFbC50ZXh0Q29udGVudCA9ICfguYDguIHguLTguJTguILguYnguK3guJzguLTguJTguJ7guKXguLLguJQ6ICcgKyBlcnIubWVzc2FnZSArICcg4LiB4Lij4Li44LiT4Liy4Lil4Lit4LiH4Lit4Li14LiB4LiE4Lij4Lix4LmJ4LiHJzsKICAgIGVyckVsLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogICAgYnRuLmRpc2FibGVkID0gZmFsc2U7CiAgICBidG4udGV4dENvbnRlbnQgPSAn4Liq4LmI4LiH4LiC4LmJ4Lit4Lih4Li54LilJzsKICB9Cn0pOwoKLy8gS2V5Ym9hcmQgc2hvcnRjdXRzCmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJpZnlFbWFpbCcpLmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLCBmdW5jdGlvbihlKSB7CiAgaWYgKGUua2V5ID09PSAnRW50ZXInKSB7IGUucHJldmVudERlZmF1bHQoKTsgc2VuZENvZGUoKTsgfQp9KTsKZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvZGVJbnB1dCcpLmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLCBmdW5jdGlvbihlKSB7CiAgaWYgKGUua2V5ID09PSAnRW50ZXInKSB7IGUucHJldmVudERlZmF1bHQoKTsgdmVyaWZ5Q29kZSgpOyB9Cn0pOwpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29kZUlucHV0JykuYWRkRXZlbnRMaXN0ZW5lcignaW5wdXQnLCBmdW5jdGlvbigpIHsKICBpZiAodGhpcy52YWx1ZS5sZW5ndGggPT09IDYpIHZlcmlmeUNvZGUoKTsKfSk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K").decode("utf-8")


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


@app.route("/landing/get-customer", methods=["POST"])
def landing_get_customer():
    data = request.get_json(force=True)
    try:
        resp = requests.post(FORWARD_URL_LANDING + "/get-customer", json=data, timeout=10)
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Nova BOT Multi-Channel Webhook ready!")
    print("  FB:  /webhook")
    print("  LINE: /linebot")
    print("  WA:   /whatsapp")
    app.run(host="0.0.0.0", port=10000, debug=False)
