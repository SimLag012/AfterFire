"""Inspect the actual deployed static chunks and verify Nginx gzip against their content."""
import gzip,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from urllib.request import Request,urlopen
with tempfile.TemporaryDirectory(prefix='afterfire-phase6-build-') as tmp:
    subprocess.run(['docker','compose','cp','frontend:/usr/share/nginx/html/.',tmp],check=True,capture_output=True)
    root=Path(tmp)
    initial=re.search(r'<script[^>]+src="([^"]+)"',(root/'index.html').read_text())[1]
    assets=[{'name':p.name,'bytes':p.stat().st_size,'gzip_bytes':len(gzip.compress(p.read_bytes(),mtime=0))} for p in (root/'assets').glob('*.js')]
    with urlopen(Request('http://localhost:3000'+initial,headers={'Accept-Encoding':'gzip'})) as response:
        encoded=response.read();encoding=response.headers.get('Content-Encoding')
        decoded=gzip.decompress(encoded) if encoding=='gzip' else encoded
    assert decoded==(root/initial.lstrip('/')).read_bytes()
    report={'initial_js':initial,'initial_raw_bytes':len(decoded),'http_encoded_bytes':len(encoded),'content_encoding':encoding,
        'javascript_chunks':len(assets),'total_javascript_bytes':sum(a['bytes'] for a in assets),
        'assets':assets,'initial_sha256':hashlib.sha256(decoded).hexdigest()}
Path('docs/phase6-bundle-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='assets'}))
