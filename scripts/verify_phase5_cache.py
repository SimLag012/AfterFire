"""Destructive cache policy verification strictly confined to a temporary directory."""
import json
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.core.config import settings
from app.services.cache_management import inventory,cleanup
from app.services.satellite_cache import active_cache
with tempfile.TemporaryDirectory(prefix='afterfire-phase5-cache-') as directory:
    root=Path(directory)/'satellite';root.mkdir()
    settings.AFTERFIRE_ANALYSIS_CACHE_DIR=str(root)
    settings.AFTERFIRE_ANALYSIS_MIN_FREE_GB=0
    settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB=8*1024*1024/1024**3
    for name in ('sources','subsets','results','processed'):(root/name).mkdir()
    (root/'sources'/'retained.hdf').write_bytes(b's'*1024*1024)
    (root/'subsets'/'replaceable.tif').write_bytes(b't'*6*1024*1024)
    (root/'subsets'/'manifest.json').write_text('{"complete":true}')
    (root/'results'/'published.tif').write_bytes(b'r'*1024*1024)
    (root/'processed'/'writing.part').write_bytes(b'active')
    firms=Path(directory)/'firms.db';firms.write_bytes(b'protected archive')
    os.link(root/'results'/'published.tif',root/'results'/'published-shared.tif')
    before,_=inventory()
    dry=cleanup()
    assert dry['recoverable_bytes']==6*1024*1024 and dry['recovered_bytes']==0
    with active_cache():
        leased=cleanup(False);assert leased['protected_by_active_lease']
    applied=cleanup(False)
    after,_=inventory()
    assert applied['recovered_bytes']==6*1024*1024
    assert (root/'results'/'published.tif').is_file() and (root/'subsets'/'manifest.json').is_file()
    assert firms.read_bytes()==b'protected archive'
    evidence={'filesystem_before':before,'dry_run':dry,'active_lease':leased,'applied':applied,
        'filesystem_after':after,'firms_archive_unchanged':True,'published_asset_available':True,
        'test_volume':'temporary directory, deleted after verification'}
    Path('docs/phase5-cache-verification.json').write_text(json.dumps(evidence,indent=2))
    print('Recovered logical bytes:',applied['recovered_bytes'],'allocated bytes:',applied['recovered_allocated_bytes'])
