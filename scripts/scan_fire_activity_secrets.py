"""Scoped pre-commit scan; reports paths/rules, never credential values."""
import json
from pathlib import Path
import re
from app.core.config import settings

root=Path('/repo')
paths=['README.md','backend/app/fire_activity','backend/app/models/fire_activity.py','backend/app/tests/test_fire_activity.py',
       'backend/app/jobs/analysis_worker.py','backend/app/main.py','backend/app/models/__init__.py',
       'frontend/src/components/fireActivity','frontend/src/pages/ExplorerPage.tsx','docs/MODIS_VIIRS_HARMONIZATION.md',
       'docs/FIRE_ACTIVITY_CALENDAR.md','docs/HARMONIZATION_VALIDATION.md','docs/fire-activity',
       'scripts/validate_fire_activity.py','scripts/publish_fire_activity_sample.py','scripts/check_fire_activity_exports.py',
       'scripts/verify_fire_activity_recovery.py','scripts/scan_fire_activity_secrets.py']
secrets=[getattr(settings,key) for key in ('FIRMS_MAP_KEY','EARTHDATA_USERNAME','EARTHDATA_PASSWORD','EARTHDATA_TOKEN','AFTERFIRE_ADMIN_TOKEN','LLM_API_KEY') if len(getattr(settings,key))>=8]
rules={'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
       'aws_access_key':r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b','github_token':r'\bgh[pousr]_[A-Za-z0-9]{30,}\b',
       'openai_token':r'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b'}
files=set()
for entry in paths:
    p=root/entry
    if p.is_dir():files.update(f for f in p.rglob('*') if f.is_file() and '__pycache__' not in f.parts)
    elif p.is_file():files.add(p)
findings=[];scanned=0
for path in sorted(files):
    if path.suffix in ('.png','.jpg','.jpeg','.pyc'):continue
    text=path.read_text();scanned+=1
    for rule,pattern in rules.items():
        if re.search(pattern,text):findings.append({'path':str(path.relative_to(root)),'rule':rule})
    if any(value in text for value in secrets):findings.append({'path':str(path.relative_to(root)),'rule':'configured_credential'})
report={'files_scanned':scanned,'findings':findings,'scope':'Task files only; configured credential values and named token/private-key patterns. No entropy scan.'}
(root/'docs/fire-activity/secret-scan.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if findings:raise SystemExit(1)
