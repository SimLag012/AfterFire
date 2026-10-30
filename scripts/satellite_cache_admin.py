"""Local administrator only: python scripts/satellite_cache_admin.py [--apply]."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.cache_management import cleanup
parser=argparse.ArgumentParser()
parser.add_argument('--apply',action='store_true',help='Apply eviction; default is dry-run')
args=parser.parse_args()
print(json.dumps(cleanup(dry_run=not args.apply),indent=2))
