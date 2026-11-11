"""Local administrator only: python scripts/satellite_cache_admin.py [--apply]."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.cache_management import cleanup
parser=argparse.ArgumentParser()
parser.add_argument('--rebuild-index',action='store_true',help='Reconcile quota index after external imports/repairs; stop old-version writers first')
parser.add_argument('--apply',action='store_true',help='Apply eviction; default is dry-run')
args=parser.parse_args()
if args.rebuild_index:
    from app.services.cache_accounting import rebuild,usage
    from app.services.satellite_cache import cache_root
    rebuild(cache_root())
    print(json.dumps(dict(index_rebuilt=True,used_results_temporary_bytes=usage(cache_root()))))
else:
    print(json.dumps(cleanup(dry_run=not args.apply),indent=2))
