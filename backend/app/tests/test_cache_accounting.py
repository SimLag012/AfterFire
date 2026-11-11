"""Quota admission and crash recovery are verified on disposable files only."""
import json
import os
import subprocess
import sys
import time

import pytest
from app.core.config import settings
from app.services import cache_accounting as ledger
from app.services.satellite_cache import cache_bytes, scan_cache_bytes


@pytest.fixture
def root(tmp_path,monkeypatch):
    path=tmp_path/'satellite';path.mkdir()
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    return path


def test_incremental_counts_hardlinks_and_removals_without_scan(root,monkeypatch):
    a=root/'processed'/'a';a.parent.mkdir();a.write_bytes(b'1234567')
    assert cache_bytes(root)==7
    monkeypatch.setattr(ledger,'_walk',lambda *_: (_ for _ in ()).throw(AssertionError('full scan')))
    b=root/'results'/'b';b.parent.mkdir()
    with ledger.mutation(root,[b],7,results=True):os.link(a,b)
    assert ledger.usage(root)==(7,7,0)
    with ledger.mutation(root,[a]):a.unlink()
    assert ledger.usage(root)==(7,7,0)
    with ledger.mutation(root,[b]):b.unlink()
    assert ledger.usage(root)==(0,0,0)


def test_exception_reconciles_partial_files_and_rejects_over_quota(root,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',10/1024**3)
    path=root/'partial.part'
    with pytest.raises(RuntimeError):
        with ledger.mutation(root,[path],8,temporary=True):
            path.write_bytes(b'12345678');raise RuntimeError('interruption')
    assert ledger.usage(root)==(8,0,8)
    with pytest.raises(ValueError,match='quota'):
        with ledger.mutation(root,[root/'another'],3):pytest.fail('admitted')
    with ledger.mutation(root,[path]):path.unlink()
    assert ledger.usage(root)==(0,0,0)


def child(root,body):
    env={**os.environ,'AFTERFIRE_ANALYSIS_CACHE_DIR':str(root),'AFTERFIRE_ANALYSIS_MIN_FREE_GB':'0',
         'AFTERFIRE_ANALYSIS_CACHE_MAX_GB':str(100/1024**3)}
    return subprocess.Popen([sys.executable,'-c',
        'from pathlib import Path; import time; from app.services.cache_accounting import mutation; '
        f'root=Path({str(root)!r}); '+body],env=env,cwd=str(__import__('pathlib').Path(ledger.__file__).resolve().parents[2]),stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def test_sigkill_dirty_index_rebuilds_before_next_admission(root):
    assert cache_bytes(root)==0
    worker=child(root,"\nwith mutation(root,[root/'native.part'],60):\n (root/'native.part').write_bytes(b'x'*60)\n print('ready',flush=True)\n time.sleep(60)\n")
    try:
        assert worker.stdout.readline().strip()==b'ready'
        worker.kill();worker.wait(timeout=5)
        assert ledger.usage(root)==(60,0,60)
        assert cache_bytes(root)==scan_cache_bytes(root)
    finally:
        if worker.poll() is None:worker.kill();worker.wait()


def test_two_processes_cannot_overcommit(root):
    assert ledger.usage(root)==(0,0,0)  # keep a parent connection open across child commits
    workers=[child(root,f"\ntry:\n with mutation(root,[root/'writer-{i}'],60):\n  time.sleep(.05)\n  (root/'writer-{i}').write_bytes(b'x'*60)\n print('accepted')\nexcept ValueError:\n print('rejected')\n") for i in range(2)]
    outputs=[]
    for worker in workers:
        out,err=worker.communicate(timeout=15)
        assert worker.returncode==0,err.decode()
        outputs.append(out.strip())
    assert sorted(outputs)==[b'accepted',b'rejected']
    assert ledger.usage(root)[0]==scan_cache_bytes(root)==60


def test_corrupt_index_rebuilds_without_losing_sources(root):
    path=root/'retained';path.write_bytes(b'valid')
    assert cache_bytes(root)==5
    index=ledger._index_path(root)
    # Simulate corruption discovered on a fresh worker, after SQLite checkpoint.
    connection=ledger._local.connections.pop(root.absolute())[0]
    connection.close()
    index.write_bytes(b'corrupt index')
    assert cache_bytes(root)==5 and path.read_bytes()==b'valid'
    assert list(root.parent.glob('*.corrupt.json'))
    assert ledger._index_path(root)!=index and index.exists()


def test_result_and_temporary_subquotas(root,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_RESULTS_MAX_GB',4/1024**3)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_TEMP_MAX_GB',4/1024**3)
    for kind in ('results','temporary'):
        with pytest.raises(ValueError,match='quota|temporary'):
            with ledger.mutation(root,[root/'new'],5,**{kind:True}):pytest.fail('admitted')


def test_attribution_context_records_geometry_and_candidate_order():
    from types import SimpleNamespace
    from datetime import date
    from shapely.geometry import box
    from app.schemas.satellite_analysis import AnalysisConfiguration
    from app.services.post_fire_pipeline import attribution_snapshot
    e=SimpleNamespace(id='fire',start_date=date(2020,1,1),end_date=date(2020,1,2),name='Fire')
    d=SimpleNamespace(id=1,longitude=10,latitude=35,acq_date=e.start_date)
    geometry=box(10,35,11,36)
    context=attribution_snapshot(e,[d],geometry,geometry,[dict(event=e,points=[(10,35)],geometry=geometry)],AnalysisConfiguration())
    assert context['target']['detections'][0]['id']==1
    assert context['candidates'][0]['geometry']['type']=='Polygon'
    assert context==attribution_snapshot(e,[d],geometry,geometry,[dict(event=e,points=[(10,35)],geometry=geometry)],AnalysisConfiguration())


def test_replaced_cache_directory_invalidates_index(root):
    path=root/'old';path.write_bytes(b'old')
    assert cache_bytes(root)==3
    root.rename(root.with_name('previous-cache'))
    root.mkdir();(root/'new').write_bytes(b'new-cache')
    assert cache_bytes(root)==9


def test_corrupt_data_page_rebuilds_when_schema_is_still_readable(root):
    (root/'native').write_bytes(b'valid')
    assert cache_bytes(root)==5
    db=ledger._local.connections.pop(root.absolute())[0]
    index=ledger._index_path(root)
    page=db.execute("SELECT rootpage FROM sqlite_master WHERE name='files'").fetchone()[0]
    page_size=db.execute('PRAGMA page_size').fetchone()[0]
    db.execute('UPDATE state SET dirty=1');db.commit()
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.close()
    with index.open('r+b') as handle:
        handle.seek((page-1)*page_size);handle.write(b'\0'*32)
    assert cache_bytes(root)==5
    assert ledger._index_path(root)!=index and index.exists()


def test_old_connection_cannot_interfere_with_replacement_generation(root):
    (root/'native').write_bytes(b'valid')
    assert cache_bytes(root)==5
    db=ledger._local.connections[root.absolute()][0]
    old=ledger._index_path(root)
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    # Keep this parent's connection open while a new process discovers corruption.
    old.write_bytes(b'corrupt header')
    worker=child(root,"\nfrom app.services.cache_accounting import usage\nprint(usage(root)[0])\n")
    out,err=worker.communicate(timeout=15)
    assert worker.returncode==0,err.decode()
    assert out.strip()==b'5' and ledger._index_path(root)!=old
    assert cache_bytes(root)==5  # closes the old cached WAL connection safely
    with ledger.mutation(root,[root/'new'],4):(root/'new').write_bytes(b'next')
    assert cache_bytes(root)==scan_cache_bytes(root)==9


def test_missing_or_corrupt_generation_pointer_never_reuses_stale_totals(root):
    (root/'native').write_bytes(b'valid')
    assert cache_bytes(root)==5
    pointer=root.parent/(root.name+'-accounting.json')
    for damage in ('corrupt','missing'):
        old=ledger._index_path(root)
        if damage=='corrupt':pointer.write_text('interrupted pointer')
        else:pointer.unlink()
        assert cache_bytes(root)==5
        assert ledger._index_path(root)!=old and old.exists()


def test_valid_source_is_not_reacquired_when_optional_evidence_cannot_fit(root,monkeypatch):
    import hashlib
    from app.services.satellite_cache import acquire
    folder=root/'sources';folder.mkdir()
    path=folder/'valid.hdf';data=b'verified-source';path.write_bytes(data)
    record={'id':'valid','original_id':'TEST.valid','product':'TEST','url':'https://unused.invalid'}
    meta={'checksum':hashlib.sha256(data).hexdigest(),'bytes':len(data),'original_id':record['original_id']}
    sidecar=path.with_suffix('.json');sidecar.write_text(json.dumps(meta))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',(len(data)+sidecar.stat().st_size)/1024**3)
    class NoDownload:
        def stream(self,*_):pytest.fail('Valid source was unnecessarily reacquired')
    cached,actual,downloaded=acquire(record,NoDownload(),1000)
    assert cached==path and actual==meta and downloaded==0
    assert path.read_bytes()==data and not list((root/'integrity').glob('*.json'))


def test_api_admission_includes_large_geometry_metadata(root,monkeypatch):
    import numpy as np
    from shapely.geometry import Point
    from app.providers.api_subsets import ApiSubsetProvider,cache_identity,subset_window
    from app.providers.appeears import LAYERS
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',100_000/1024**3)
    geometry=Point(15,37).buffer(.001,quad_segs=5000)
    record={'id':'metadata-bound','product':'MOD13Q1','version':'061','tile':'h19v05',
            'original_id':'MOD13Q1.A2020225.h19v05.061.2021001000000.hdf',
            'period':{'start':'2020-08-12'}}
    key,spec=cache_identity(record,geometry);win,affine=subset_window(record,geometry)
    arrays={name:np.zeros((int(win.height),int(win.width)),dtype='int32') for name in LAYERS['MOD13Q1']}
    assert sum(a.nbytes for a in arrays.values())+65536<100_000
    with pytest.raises(ValueError,match='quota'):
        ApiSubsetProvider()._publish(record,geometry,arrays,sum(a.nbytes for a in arrays.values()),win,affine,key,spec,root/'api-subsets'/key)
    assert ledger.usage(root)[0]==0
    assert not list(root.rglob('native.tif')) and not list(root.rglob('source.json'))
