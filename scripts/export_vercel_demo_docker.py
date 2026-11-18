"""Export through the existing LOCAL backend container. Never uploads or deploys."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
from check_vercel_clone import check

ROOT=Path(__file__).resolve().parents[1]


def run(*args):subprocess.run(args,check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--container',default='afterfire-clean-backend-1');p.add_argument('--selection',type=Path,default=ROOT/'scripts/vercel_demo_selection.json');p.add_argument('--output',type=Path,default=ROOT/'public-demo/public/demo');p.add_argument('--max-mb',type=int,default=80);args=p.parse_args()
    context=json.loads(subprocess.check_output(['docker','context','inspect']))[0];host=os.environ.get('DOCKER_HOST') or context['Endpoints']['docker']['Host']
    if not host.startswith(('unix://','npipe://')):raise SystemExit('A local Docker daemon is required; remote uploads are forbidden')
    out=args.output.resolve()
    if out.exists() and not (out/'.afterfire-export').is_file():raise SystemExit('Refusing to overwrite an unowned directory')
    out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.afterfire-export-',dir=out.parent));token=uuid.uuid4().hex
    remote='/tmp/afterfire-vercel-'+token;script=remote+'.py';selection=remote+'-selection.json';backup=out.with_name(out.name+'.previous')
    try:
        run('docker','cp',str(ROOT/'scripts/export_vercel_demo.py'),args.container+':'+script)
        run('docker','cp',str(args.selection.resolve()),args.container+':'+selection)
        run('docker','exec','-e','PYTHONPATH=/app',args.container,'python',script,'--selection',selection,'--output',remote,'--max-mb',str(args.max_mb))
        run('docker','cp',args.container+':'+remote+'/.',str(stage));check(stage,check_ui=False)
        if backup.exists():raise RuntimeError('Inspect the previous backup before retrying')
        if out.exists():out.rename(backup)
        try:stage.rename(out)
        except BaseException:
            if backup.exists():backup.rename(out)
            raise
        if backup.exists():shutil.rmtree(backup)
    finally:
        if stage.exists():shutil.rmtree(stage)
        run('docker','exec',args.container,'python','-c','import pathlib,shutil,sys;shutil.rmtree(sys.argv[1],ignore_errors=True);[pathlib.Path(p).unlink(missing_ok=True) for p in sys.argv[2:]]',remote,script,selection)


if __name__=='__main__':main()
