#!/usr/bin/env python3
"""
Google Drive Backup — Immigration System
Backs up: Customer DB, Social BOT messages, scripts
Schedule: Runs with heartbeat or manually

Max file size configurable via environment variable MAX_BACKUP_SIZE_MB.
Set to 0 for unlimited.
"""

import json
import os
import pickle
import sys
import datetime
import hashlib
from dotenv import load_dotenv
load_dotenv()

# Configurable paths
BASE_DIR = os.getenv("BASE_DIR", r"D:\ImmigrationCases")
OPENCLAW_DATA_DIR = os.getenv("OPENCLAW_DATA_DIR", r"D:\OpenClawData")

# Google Drive credentials
CREDENTIALS_FILE = os.getenv("GDRIVE_CREDENTIALS", os.path.join(OPENCLAW_DATA_DIR, ".openclaw/gmail/credentials.json"))
TOKENS_DIR = os.getenv("GDRIVE_TOKENS_DIR", os.path.join(OPENCLAW_DATA_DIR, ".openclaw/gmail/tokens"))
DRIVE_TOKEN_FILE = os.path.join(TOKENS_DIR, "drive.pickle")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Maximum file size to upload (in MB). Set to 0 for unlimited.
MAX_BACKUP_SIZE_MB = int(os.getenv("MAX_BACKUP_SIZE_MB", "200"))

# What to backup (using environment variables)
BACKUP_SOURCES = {
    "ImmigrationCases": BASE_DIR,
    "SocialBOT": os.getenv("SOCIAL_BOT_DIR", r"D:\Social BOT"),
    "Scripts": os.getenv("SCRIPTS_DIR", os.path.join(OPENCLAW_DATA_DIR, "workspace")),
}

# Exclude only temporary/cache files
EXCLUDE_PATTERNS = ["__pycache__", ".pyc", ".log", "_processed_", "_dedup_", "_backup_", "_drive_"]

DEDUP_FILE = os.getenv("DEDUP_FILE", os.path.join(BASE_DIR, "_drive_dedup.json"))
REPORT_FILE = os.getenv("BACKUP_REPORT_FILE", os.path.join(BASE_DIR, "_backup_report.json"))

# Ensure tokens directory exists
os.makedirs(TOKENS_DIR, exist_ok=True)

def get_drive_service():
    """Get authenticated Google Drive service"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(DRIVE_TOKEN_FILE):
        with open(DRIVE_TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)

    if creds and creds.valid:
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(DRIVE_TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    # Need new auth
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    with open(DRIVE_TOKEN_FILE, 'wb') as f:
        pickle.dump(creds, f)
    print("[DRIVE] New token saved.")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def ensure_folder(service, folder_name, parent_id=None):
    """Create folder in Drive if not exists, return folder ID"""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, spaces='drive', fields='files(id,name)').execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    meta = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        meta['parents'] = [parent_id]

    folder = service.files().create(body=meta, fields='id').execute()
    return folder['id']


def file_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def load_dedup():
    if os.path.exists(DEDUP_FILE):
        with open(DEDUP_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_dedup(dedup):
    with open(DEDUP_FILE, 'w') as f:
        json.dump(dedup, f, indent=2)


def upload_file(service, filepath, parent_id, dedup):
    """Upload a file to Drive, skip if already backed up"""
    fhash = file_hash(filepath)
    rel_path = os.path.basename(filepath)
    
    if fhash in dedup:
        return None, 'already backed up'

    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(filepath, resumable=True)
    
    try:
        file = service.files().create(
            body={'name': rel_path, 'parents': [parent_id]},
            media_body=media,
            fields='id,name,size'
        ).execute()
        
        dedup[fhash] = {
            'path': filepath,
            'drive_id': file['id'],
            'size': os.path.getsize(filepath),
            'backed_up': datetime.datetime.now().isoformat()
        }
        return file, None
    except Exception as e:
        return None, str(e)


def run_backup():
    """Main backup function"""
    print(f"\n=== GOOGLE DRIVE BACKUP - {datetime.datetime.now().isoformat()} ===")
    
    if MAX_BACKUP_SIZE_MB > 0:
        print(f"Max file size: {MAX_BACKUP_SIZE_MB} MB (set MAX_BACKUP_SIZE_MB=0 for unlimited)")
    else:
        print("Max file size: UNLIMITED (set MAX_BACKUP_SIZE_MB=0)")
    
    dedup = load_dedup()
    service = get_drive_service()
    
    # Get account info
    about = service.about().get(fields="user(displayName,emailAddress)").execute()
    user = about.get('user', {})
    print(f"Account: {user.get('displayName','?')} ({user.get('emailAddress','?')})")
    
    # Create root folder
    root_id = ensure_folder(service, "NovaBot_Backup")
    print(f"Root folder: NovaBot_Backup (ID: {root_id})")
    
    # Create date-stamped backup folder
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    backup_id = ensure_folder(service, date_str, root_id)
    print(f"Date folder: {date_str}")
    
    stats = {'uploaded': 0, 'skipped': 0, 'errors': 0, 'bytes': 0}
    
    for label, source_dir in BACKUP_SOURCES.items():
        if not os.path.exists(source_dir):
            print(f"  [SKIP] {label}: directory not found")
            continue
        
        label_id = ensure_folder(service, label, backup_id)
        print(f"\n  [{label}] {source_dir}")
        
        for root, dirs, files in os.walk(source_dir):
            # Skip excluded patterns in folder names
            dirs[:] = [d for d in dirs if not any(p in d for p in EXCLUDE_PATTERNS)]
            
            rel = os.path.relpath(root, source_dir)
            current_parent = label_id
            
            if rel != '.':
                for part in rel.split(os.sep):
                    if part.startswith('_'):
                        pass
                    current_parent = ensure_folder(service, part, current_parent)
            
            for f in sorted(files):
                # Skip temporary / metadata files
                if any(f.startswith(p) or f.endswith(p) for p in EXCLUDE_PATTERNS):
                    continue
                
                fpath = os.path.join(root, f)
                size = os.path.getsize(fpath)
                max_bytes = MAX_BACKUP_SIZE_MB * 1024 * 1024
                if MAX_BACKUP_SIZE_MB > 0 and size > max_bytes:
                    print(f"    [SKIP] {f} (too large: {size/1024/1024:.1f}MB > {MAX_BACKUP_SIZE_MB}MB)")
                    stats['skipped'] += 1
                    continue
                
                result, error = upload_file(service, fpath, current_parent, dedup)
                
                if result:
                    stats['uploaded'] += 1
                    stats['bytes'] += size
                    print(f"    [OK] {f} ({size/1024:.1f}KB)")
                elif error == 'already backed up':
                    stats['skipped'] += 1
                else:
                    stats['errors'] += 1
                    print(f"    [FAIL] {f}: {error}")
    
    save_dedup(dedup)
    
    # Save report
    report = {
        'timestamp': datetime.datetime.now().isoformat(),
        'account': user.get('emailAddress', '?'),
        'stats': stats,
        'dedup_count': len(dedup)
    }
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n=== BACKUP COMPLETE ===")
    print(f"Uploaded: {stats['uploaded']} files ({stats['bytes']/1024/1024:.1f}MB)")
    print(f"Skipped (dedup/size): {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"Total tracked: {len(dedup)} files")
    
    return stats


def cmd_stats():
    """Show backup stats"""
    dedup = load_dedup()
    print(f"\n=== DRIVE BACKUP STATS ===")
    print(f"Total files tracked: {len(dedup)}")
    
    # Group by customer
    by_customer = {}
    total_bytes = 0
    for fhash, info in dedup.items():
        path = info.get('path', '')
        size = info.get('size', 0)
        total_bytes += size
        parts = path.split(os.sep)
        if len(parts) > 3:
            cust = parts[3] if len(parts) > 3 else 'unknown'
        else:
            cust = 'unknown'
        if cust not in by_customer:
            by_customer[cust] = {'files': 0, 'bytes': 0}
        by_customer[cust]['files'] += 1
        by_customer[cust]['bytes'] += size
    
    print(f"Total size: {total_bytes/1024/1024:.1f} MB")
    print(f"\nBy folder:")
    for cust, info in sorted(by_customer.items()):
        print(f"  {cust}: {info['files']} files ({info['bytes']/1024/1024:.1f} MB)")
    
    if os.path.exists(REPORT_FILE):
        with open(REPORT_FILE) as f:
            report = json.load(f)
        print(f"\nLast backup: {report.get('timestamp','?')}")
        print(f"Account: {report.get('account','?')}")


def cmd_verify():
    """Verify local files against Drive backup"""
    dedup = load_dedup()
    print(f"\n=== VERIFY LOCAL VS DRIVE ===")
    
    missing_local = 0
    ok = 0
    
    for fhash, info in dedup.items():
        local_path = info.get('path', '')
        if os.path.exists(local_path):
            h = hashlib.sha256()
            with open(local_path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    h.update(chunk)
            if h.hexdigest() == fhash:
                ok += 1
            else:
                print(f"  [CHANGED] {local_path}")
        else:
            print(f"  [MISSING] {local_path}")
            missing_local += 1
    
    print(f"\nOK: {ok}, Missing locally: {missing_local}, Total: {len(dedup)}")
    return ok, missing_local


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'stats':
            cmd_stats()
        elif cmd == 'verify':
            cmd_verify()
        elif cmd == 'backup':
            run_backup()
        else:
            print('Commands: backup, stats, verify')
    else:
        run_backup()
