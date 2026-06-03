#!/usr/bin/env python3
"""Message Consolidation System - cross-channel customer message consolidation"""
import json, os, shutil, datetime, sys, argparse, hashlib

SOCIAL_BOT_DIR = r"D:\Social BOT"
CUSTOMERS_DB = r"D:\ImmigrationCases\_Customers.json"
CUSTOMERS_DIR = r"D:\ImmigrationCases"

def load_customers():
    if not os.path.exists(CUSTOMERS_DB):
        return {'schema_version': '1.0', 'last_updated': '', 'customers': [], 'customers_by_channel': {}}
    with open(CUSTOMERS_DB, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_customers(db):
    db['last_updated'] = datetime.datetime.now().isoformat()
    with open(CUSTOMERS_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def parse_sender(folder_name):
    if folder_name.startswith('FB_'): return ('messenger', folder_name[3:])
    if folder_name.startswith('WA_'): return ('whatsapp', folder_name[3:])
    return (None, None)

def find_customer(db, channel_type, sender_id):
    key = f'{channel_type}:{sender_id}'
    return db['customers_by_channel'].get(key)

# ── Dedup System ────────────────────────────────────────

def file_hash(filepath):
    """SHA256 hash of file content"""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def get_dedup_db():
    """Load the dedup database (content hash -> list of known paths)"""
    dedup_file = os.path.join(CUSTOMERS_DIR, '_dedup.json')
    if os.path.exists(dedup_file):
        with open(dedup_file, 'r') as f:
            return json.load(f)
    return {'hashes': {}, 'by_customer': {}}

def save_dedup_db(db):
    dedup_file = os.path.join(CUSTOMERS_DIR, '_dedup.json')
    with open(dedup_file, 'w') as f:
        json.dump(db, f, indent=2)

def is_duplicate(filepath, cust_id, dedup_db):
    """
    Check if a file is a duplicate. Returns:
      - None if unique (not duplicate)
      - str with detail if duplicate (e.g. 'same as C003/2026-06-03/passport.jpg from LINE')
    """
    if not os.path.isfile(filepath):
        return None
    
    fhash = file_hash(filepath)
    
    if fhash in dedup_db['hashes']:
        existing = dedup_db['hashes'][fhash]
        # Check if this exact path was already recorded
        if filepath not in existing.get('paths', []):
            existing['paths'].append(filepath)
        existing['count'] = len(existing.get('paths', []))
        save_dedup_db(dedup_db)
        
        # Return info about where the first copy was stored
        stored = existing.get('stored_at', 'unknown')
        source = existing.get('source_channel', 'unknown')
        return f"duplicate (first seen in {stored}, via {source})"
    
    return None  # Unique file

def mark_as_processed(filepath, cust_id, dest_path, channel, dedup_db):
    """Record a file in the dedup database after copying it"""
    if not os.path.isfile(filepath):
        return
    
    fhash = file_hash(filepath)
    
    dedup_db['hashes'][fhash] = {
        'paths': [filepath],
        'stored_at': dest_path,
        'source_channel': channel,
        'customer_id': cust_id,
        'first_seen': datetime.datetime.now().isoformat(),
        'count': 1
    }
    
    if cust_id not in dedup_db['by_customer']:
        dedup_db['by_customer'][cust_id] = []
    dedup_db['by_customer'][cust_id].append({
        'hash': fhash,
        'path': dest_path,
        'channel': channel,
        'size': os.path.getsize(filepath)
    })
    
    save_dedup_db(dedup_db)


# ── Copy with Dedup ─────────────────────────────────────

def copy_to_customer(src_path, customer_id, channel_type, prefix, dedup_db):
    """Copy a file to customer folder with duplicate detection"""
    now = datetime.datetime.now()
    cust_dir = os.path.join(CUSTOMERS_DIR, customer_id)
    day_dir = os.path.join(cust_dir, now.strftime('%Y-%m-%d'))
    os.makedirs(day_dir, exist_ok=True)
    
    # For non-image/json files, check dedup
    is_binary = src_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx'))
    
    if is_binary:
        dup_info = is_duplicate(src_path, customer_id, dedup_db)
        if dup_info:
            return None, dup_info  # Duplicate, not copied
    
    ext = os.path.splitext(src_path)[1]
    fname = f'{prefix}_{channel_type}_{now.strftime("%H%M%S")}{ext}'
    dest = os.path.join(day_dir, fname)
    
    # Also check by filename content for JSON message files
    if not is_binary and os.path.exists(dest):
        # For JSON message files, check if content is same
        with open(src_path, 'r', encoding='utf-8') as f:
            src_content = f.read()
        with open(dest, 'r', encoding='utf-8') as f:
            dst_content = f.read()
        if src_content == dst_content:
            return None, 'duplicate content'
    
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copy2(src_path, dest)
    
    # Mark binary files in dedup DB
    if is_binary:
        mark_as_processed(src_path, customer_id, dest, channel_type, dedup_db)
    
    return dest, None


# ── Processing State ────────────────────────────────────

def get_processed():
    pf = os.path.join(CUSTOMERS_DIR, '_processed.json')
    if os.path.exists(pf):
        with open(pf, 'r') as f: return set(json.load(f))
    return set()

def save_processed(s):
    pf = os.path.join(CUSTOMERS_DIR, '_processed.json')
    with open(pf, 'w') as f: json.dump(list(s), f)


# ── Main Consolidation ──────────────────────────────────

def _rebuild_dedup_from_disk(dedup_db):
    scanned = 0
    for root, dirs, files in os.walk(CUSTOMERS_DIR):
        rel = os.path.relpath(root, CUSTOMERS_DIR)
        parts = rel.split(os.sep)
        if len(parts) < 1: continue
        cust_id = parts[0]
        if cust_id.startswith('_'): continue
        for f in files:
            fpath = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx'): continue
            h = hashlib.sha256()
            try:
                with open(fpath, 'rb') as fh:
                    for chunk in iter(lambda: fh.read(65536), b''): h.update(chunk)
            except: continue
            fhash = h.hexdigest()
            if fhash in dedup_db['hashes']: continue
            channel = 'unknown'
            if f.startswith('att_line_'): channel = 'line'
            elif f.startswith('att_messenger_'): channel = 'messenger'
            elif f.startswith('att_whatsapp_'): channel = 'whatsapp'
            elif f.startswith('House'): channel = 'email'
            dedup_db['hashes'][fhash] = {
                'paths': [fpath], 'stored_at': fpath, 'source_channel': channel,
                'customer_id': cust_id, 'first_seen': 'rebuild', 'count': 1
            }
            scanned += 1
    print('  [DEDUP] Scanned {} existing files'.format(scanned))
    return dedup_db

def consolidate():
    db = load_customers()
    dedup_db = get_dedup_db()
    # Rebuild dedup DB from existing files to prevent re-copying
    dedup_db = _rebuild_dedup_from_disk(dedup_db)
    processed = get_processed()
    results = []
    unknowns = set()
    knowns = set()
    duplicates = []
    line_processed_path = os.path.join(CUSTOMERS_DIR, '_processed_line.json')

    processed_line = set()
    if os.path.exists(line_processed_path):
        with open(line_processed_path) as f: processed_line = set(json.load(f))

    if not os.path.exists(SOCIAL_BOT_DIR):
        return results, unknowns, knowns, duplicates

    for folder in os.listdir(SOCIAL_BOT_DIR):
        fpath = os.path.join(SOCIAL_BOT_DIR, folder)
        if not os.path.isdir(fpath): continue
        ch, sid = parse_sender(folder)
        if not ch: continue

        for root, dirs, files in os.walk(fpath):
            for fn in files:
                fp = os.path.join(root, fn)
                if fp in processed: continue
                if not fn.endswith('.json'): continue
                processed.add(fp)

                try:
                    with open(fp, 'r', encoding='utf-8') as f: msg = json.load(f)
                except: continue

                cid = find_customer(db, ch, sid)
                txt = msg.get('text', '(non-text)')[:80]
                
                # Check for attachments in message JSON
                atts = msg.get('attachments', [])
                
                if cid:
                    dest, dup = copy_to_customer(fp, cid, ch, 'msg', dedup_db)
                    knowns.add(cid)
                    if dup:
                        duplicates.append({'file': fp, 'channel': ch, 'reason': dup})
                        results.append({'customer': cid, 'channel': ch, 'text': txt, 'dest': str(dest) if dest else '(dedup)', 'status': 'dedup'})
                    else:
                        results.append({'customer': cid, 'channel': ch, 'text': txt, 'dest': str(dest), 'status': 'new'})
                        
                    # Also process downloaded attachment images (from FB_local_download)
                    for att in atts:
                        att_url = att.get('payload', {}).get('url', '')
                        if att_url:
                            # Attachments are already downloaded by fb_local_download
                            att_files = [f for f in os.listdir(root) if f.startswith('FB_att_') and f.endswith(('.jpg','.png','.jpeg'))]
                            for af in att_files:
                                afp = os.path.join(root, af)
                                if afp in processed: continue
                                processed.add(afp)
                                dest, dup = copy_to_customer(afp, cid, ch, 'att', dedup_db)
                                if dup:
                                    duplicates.append({'file': afp, 'channel': ch, 'reason': dup})
                                else:
                                    pass  # Already counted in results
                else:
                    unknowns.add((ch, sid))
                    results.append({'customer': 'UNKNOWN', 'channel': ch, 'sender': sid, 'text': txt, 'status': 'new'})

    # LINE log processing
    line_log = os.path.join(SOCIAL_BOT_DIR, '_line_messages.log')
    if os.path.exists(line_log):
        with open(line_log, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    entry = json.loads(line)
                except: continue
                uid = f'{entry.get("time","")}_{entry.get("text","")}_{entry.get("saved_to","")}'
                if uid in processed_line: continue
                processed_line.add(uid)

                user_id = entry.get('user_id', '')
                cid = find_customer(db, 'line', user_id)
                txt = entry.get('text', '') or f'({entry.get("type","unknown")})'

                saved = entry.get('saved_to', '')
                if saved and os.path.exists(saved) and cid:
                    dest, dup = copy_to_customer(saved, cid, 'line', 'att', dedup_db)
                    if dup:
                        duplicates.append({'file': saved, 'channel': 'line', 'reason': dup})
                    else:
                        pass

                if cid:
                    knowns.add(cid)
                    results.append({'customer': cid, 'channel': 'line', 'text': txt[:80], 'status': 'new'})
                else:
                    unknowns.add(('line', user_id))
                    results.append({'customer': 'UNKNOWN', 'channel': 'line', 'sender': user_id, 'text': txt[:80], 'status': 'new'})

    save_processed(processed)
    with open(line_processed_path, 'w') as f: json.dump(list(processed_line), f)
    return results, unknowns, knowns, duplicates


# ── Customer Management ─────────────────────────────────

def add_customer(name, phone='', email='', messenger_id='', whatsapp_num='', line_ids=None):
    if line_ids is None: line_ids = []
    db = load_customers()
    existing = None
    for c in db['customers']:
        if c['profile']['name'] == name:
            existing = c; break
    if existing:
        cid = existing['customerId']
        if messenger_id: existing['channels']['messenger'] = messenger_id
        if whatsapp_num: existing['channels']['whatsapp'] = whatsapp_num
        if line_ids: existing['channels']['line'] = list(set(existing['channels']['line'] + line_ids))
        if phone: existing['profile']['phone'] = phone
        if email: existing['profile']['email'] = email
        existing['updatedAt'] = datetime.datetime.now().isoformat()
        action = 'Updated'
    else:
        cid = f"C{len(db['customers'])+1:03d}"
        existing = {'customerId': cid, 'profile': {'name': name, 'phone': phone, 'email': email},
                     'channels': {'messenger': messenger_id or '', 'whatsapp': whatsapp_num or '', 'line': line_ids},
                     'createdAt': datetime.datetime.now().isoformat(), 'updatedAt': datetime.datetime.now().isoformat()}
        db['customers'].append(existing)
        action = 'Created'
    
    # Rebuild channel map + email map
    db['customers_by_channel'] = {}
    for c in db['customers']:
        for k in ['messenger', 'whatsapp']:
            v = c['channels'].get(k, '')
            if v: db['customers_by_channel'][f'{k}:{v}'] = c['customerId']
        for lid in c['channels'].get('line', []):
            if lid: db['customers_by_channel'][f'line:{lid}'] = c['customerId']
        email = c['profile'].get('email', '')
        if email: db['customers_by_channel'][f'email:{email}'] = c['customerId']
    
    save_customers(db)
    print(f'{action} {cid} - {name}')
    return cid


def list_customers():
    db = load_customers()
    dedup_db = get_dedup_db()
    print(f'== Customer DB ({len(db["customers"])} customers) ==')
    for c in db['customers']:
        ch = c['channels']
        chs = []
        if ch.get('messenger'): chs.append(f'FB:{ch["messenger"]}')
        if ch.get('whatsapp'): chs.append(f'WA:{ch["whatsapp"]}')
        if ch.get('line'): chs.append(f'LINE:{len(ch["line"])} ids')
        print(f'  {c["customerId"]} - {c["profile"]["name"]}')
        print(f'    Phone: {c["profile"].get("phone","-")} Email: {c["profile"].get("email","-")}')
        print(f'    Channels: {" | ".join(chs) if chs else "(none)"}')
    print(f'Channel map: {len(db["customers_by_channel"])} entries')
    
    # Show dedup stats
    total_hashes = len(dedup_db.get('hashes', {}))
    total_dups = sum(1 for v in dedup_db.get('hashes', {}).values() if v.get('count', 1) > 1)
    if total_hashes > 0:
        print(f'Dedup DB: {total_hashes} files tracked, {total_dups} duplicates caught')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'add':
        p = argparse.ArgumentParser()
        p.add_argument('add', help='add command')
        p.add_argument('name', help='Customer name')
        p.add_argument('--phone', default='')
        p.add_argument('--email', default='')
        p.add_argument('--messenger', default='')
        p.add_argument('--whatsapp', default='')
        p.add_argument('--line', default='')
        args = p.parse_args()
        lids = [x.strip() for x in args.line.split(',') if x.strip()]
        add_customer(args.name, args.phone, args.email, args.messenger, args.whatsapp, lids)
    elif len(sys.argv) > 1 and sys.argv[1] == 'list':
        list_customers()
    elif len(sys.argv) > 1 and sys.argv[1] == 'stats':
        dedup_db = get_dedup_db()
        print(f'Dedup DB: {len(dedup_db.get("hashes",{}))} unique file hashes')
        for h, v in dedup_db.get('hashes', {}).items():
            if v.get('count', 1) > 1:
                print(f'  DUPLICATE x{v["count"]}: {v["source_channel"]} -> {v["stored_at"]}')
        print(f'By customer:')
        for cid, files in dedup_db.get('by_customer', {}).items():
            print(f'  {cid}: {len(files)} unique files')
    else:
        now = datetime.datetime.now().isoformat()
        print(f'== CONSOLIDATION RUN - {now} ==')
        msgs, unknowns, knowns, dups = consolidate()
        print(f'== Results: {len(knowns)} known, {len(unknowns)} unknown, {len(msgs)} msgs ==')
        
        new_count = sum(1 for m in msgs if m.get('status') != 'dedup')
        dedup_count = sum(1 for m in msgs if m.get('status') == 'dedup')
        print(f'   New: {new_count} | Deduplicated: {dedup_count}')
        
        for m in msgs:
            c = m['customer']
            tag = 'V' if c != 'UNKNOWN' else '?'
            status = m.get('status', '')
            status_tag = ' [DUP]' if status == 'dedup' else ''
            ch = m['channel']
            tx = m.get('text','')[:60]
            if c == 'UNKNOWN':
                print(f'  [{tag}]{status_tag} [{ch}] {m.get("sender","?")}: "{tx}"')
            else:
                print(f'  [{tag}]{status_tag} [{ch}] -> {c}: "{tx}"')
        
        if dups:
            print(f'\n== DUPLICATES DETECTED ({len(dups)}) ==')
            for d in dups[:10]:
                print(f'  * {os.path.basename(d["file"])} ({d["channel"]}): {d["reason"]}')
        
        if unknowns:
            print('== UNKNOWN senders (need mapping) ==')
            for ch, sid in sorted(unknowns):
                print(f'  * {ch}:{sid}')
        print(f'== Done ==')
