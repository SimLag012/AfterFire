"""Release gates must reject private ADC/database assets without printing secrets."""
import runpy
import json
from pathlib import Path


def test_release_scanner_rejects_private_assets_and_adc_content():
    scan=runpy.run_path(str(Path(__file__).resolve().parents[3]/'scripts/check_secrets.py'))['findings']
    assert scan('application_default_credentials.json',b'{}')
    assert scan('snapshot.db',b'fixture')
    assert scan('native.tif',b'fixture')
    assert scan('unexpected.json',json.dumps(dict(refresh_token='fixture-token-never-valid')).encode())
    assert scan('unexpected.json',json.dumps(dict(client_secret='fixture-secret-never-valid')).encode())
    assert not scan('example.json',b'{"client_secret":"placeholder"}')
    assert not scan('docs/public-verification.json',b'{"status":"verified"}')
