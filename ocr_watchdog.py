#!/usr/bin/env python3
"""
Watchdog for OCR pending folder.
Monitors <BASE_DIR>/_pending_ocr
When a .meta file appears, send its content to OpenClaw classify endpoint.
Includes startup scan to process leftover files.
Renames .meta to .meta.sent after successful send.
"""

import os
import json
import time
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
load_dotenv()

# Configurable paths
BASE_DIR = os.getenv("BASE_DIR", r"D:\ImmigrationCases")
PENDING_DIR = os.path.join(BASE_DIR, "_pending_ocr")
OPENCLAW_CLASSIFY_URL = os.getenv("OPENCLAW_CLASSIFY_URL", "http://localhost:5006/classify")

os.makedirs(PENDING_DIR, exist_ok=True)

class MetaFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.meta'):
            time.sleep(0.5)
            self.process_meta(event.src_path)

    def process_meta(self, meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            pending_file = meta.get('pending_file')
            if not pending_file or not os.path.exists(pending_file):
                print(f"[ERROR] Pending file not found: {pending_file}")
                os.rename(meta_path, meta_path + ".missing")
                return

            payload = {
                "filepath": pending_file,
                "customer_id": meta.get("customer_id"),
                "display_id": meta.get("display_id"),
                "original_filename": meta.get("original_filename"),
                "original_filepath": meta.get("original_filepath")
            }
            resp = requests.post(OPENCLAW_CLASSIFY_URL, json=payload, timeout=30)
            if resp.status_code == 200:
                print(f"[OK] Sent to OpenClaw: {pending_file}")
                os.rename(meta_path, meta_path + ".sent")
            else:
                print(f"[ERROR] OpenClaw returned {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[ERROR] Processing {meta_path}: {e}")

def startup_scan(handler):
    print("Startup scan: looking for existing .meta files...")
    for filename in os.listdir(PENDING_DIR):
        if filename.endswith('.meta') and not filename.endswith('.sent') and not filename.endswith('.missing'):
            meta_path = os.path.join(PENDING_DIR, filename)
            print(f"Found pending file: {meta_path}")
            handler.process_meta(meta_path)
    print("Startup scan completed.")

if __name__ == "__main__":
    print(f"Watching {PENDING_DIR} for .meta files...")
    print(f"Classifier URL: {OPENCLAW_CLASSIFY_URL}")
    event_handler = MetaFileHandler()
    startup_scan(event_handler)
    observer = Observer()
    observer.schedule(event_handler, PENDING_DIR, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
