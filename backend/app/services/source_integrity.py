"""Cross-process integrity evidence; a filename or size alone never establishes trust."""
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from app.core.config import settings
from app.services.satellite_cache import cache_root, file_lock
from app.services.planning_metrics import record

from app.services.cache_accounting import atomic_json

VALIDATOR = 'source-integrity-6.1'


def fingerprint(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def verify(path, entry, identity, validator=None, force=False):
    path = Path(path)
    checksum = entry.get('checksum', '')
    if not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}', checksum):
        return False
    key = hashlib.sha256(str(path.absolute()).encode()).hexdigest()
    root = cache_root() / 'integrity'
    root.mkdir(parents=True, exist_ok=True)
    evidence = root / (key + '.json')
    waiting = time.monotonic()
    with file_lock(root / (key + '.lock')):
        record('integrity_lock_seconds', time.monotonic() - waiting)
        try:
            started = time.monotonic()
            if path.is_symlink():
                return False
            generation = fingerprint(path)
            record('integrity_stat_seconds', time.monotonic() - started)
            record('integrity_files', 1)
            if generation[2] != entry['bytes']:
                return False
            # Includes the full manifest entry and the scientific validator identity.
            trust = {'entry': entry, 'identity': identity, 'validator': VALIDATOR}
            try:
                saved = json.loads(evidence.read_text())
                if (not force and saved['trust'] == trust and saved['fingerprint'] == generation
                        and 0 <= time.time()-saved['at'] < settings.AFTERFIRE_CATALOG_CACHE_TTL_HOURS*3600):
                    record('integrity_hits', 1)
                    return True
            except (OSError, ValueError, KeyError):
                pass
            started = time.monotonic()
            with path.open('rb') as handle:
                actual = hashlib.file_digest(handle, 'sha256').hexdigest()
            record('integrity_bytes_read', generation[2])
            record('integrity_sha256', 1)
            record('integrity_hash_seconds', time.monotonic()-started)
            if actual != checksum:
                return False
            if validator:
                validator()
            if fingerprint(path) != generation:
                return False
            try:
                atomic_json(evidence, {'trust': trust, 'fingerprint': generation, 'at': time.time()})
            except (OSError,ValueError,sqlite3.DatabaseError):
                # Bytes, identity and science validator have already passed. An
                # optional evidence-cache write must never trigger reacquisition.
                record('integrity_evidence_write_skipped',1)
            return True
        except (OSError, ValueError, KeyError):
            return False


def verify_manifest(folder, manifest):
    """One evidence read per bundle; every file generation is still checked on every use."""
    folder=Path(folder)
    if not isinstance(manifest,dict):return False
    entries=manifest.get('files',[])
    if manifest.get('complete') is not True or not isinstance(entries,list) or not entries or any(not isinstance(e,dict) for e in entries):
        return False
    names=[e.get('name','') for e in entries]
    if any(not isinstance(n,str) for n in names):return False
    if len(set(names))!=len(names) or any(not n or Path(n).name!=n for n in names):
        return False
    if any(not isinstance(e.get('checksum'),str) or not re.fullmatch('[0-9a-f]{64}',e['checksum']) or type(e.get('bytes')) is not int or e['bytes']<0 for e in entries):
        return False
    root=cache_root()/'integrity';root.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(str(folder.absolute()).encode()).hexdigest()
    evidence=root/('manifest-'+key+'.json')
    trust=hashlib.sha256(json.dumps({'manifest':manifest,'validator':VALIDATOR},sort_keys=True).encode()).hexdigest()
    with file_lock(evidence.with_suffix('.lock')):
        try:
            generation={}
            started=time.monotonic()
            for entry in entries:
                path=folder/entry['name']
                if path.is_symlink():return False
                current=fingerprint(path)
                if current[2]!=entry['bytes']:return False
                generation[entry['name']]=current
            record('integrity_stat_seconds',time.monotonic()-started)
            record('integrity_manifest_files',len(entries))
            try:saved=json.loads(evidence.read_text())
            except (OSError,ValueError):saved={}
            fresh=(saved.get('trust')==trust and 0<=time.time()-saved.get('at',0)<settings.AFTERFIRE_CATALOG_CACHE_TTL_HOURS*3600)
            if fresh and saved.get('fingerprints')==generation:
                record('integrity_manifest_hits',1)
                return True
            for entry in entries:
                name=entry['name']
                if fresh and saved.get('fingerprints',{}).get(name)==generation[name]:continue
                if not verify(folder/name,entry,{'adapter':1,'subset':folder.name},force=True):return False
            # Do not extend the age of unchanged evidence when only one file changed.
            at=saved['at'] if fresh else time.time()
            if any(fingerprint(folder/n)!=generation[n] for n in names):return False
            try:
                atomic_json(evidence, {'trust':trust,'fingerprints':generation,'at':at})
            except (OSError,ValueError,sqlite3.DatabaseError):
                record('integrity_evidence_write_skipped',1)
            return True
        except (OSError,ValueError,KeyError,TypeError):
            return False
