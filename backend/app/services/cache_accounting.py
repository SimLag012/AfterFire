"""Rebuildable SQLite quota index, serialized with the cache's cross-process lock.

Every cache mutation must use mutation(). Its durable dirty bit precedes filesystem
changes. A killed writer or damaged index forces reconciliation before admission.
The sidecar DB lives beside the cache, so it is never an eviction candidate.
"""
import os
import json
import uuid
import sqlite3
import threading
import time
from contextlib import contextmanager
from collections import OrderedDict
from pathlib import Path

_local = threading.local()


def _walk(root):
    pending=[root]
    while pending:
        folder=pending.pop()
        if folder.is_symlink():
            continue
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.is_symlink():continue
                    if entry.is_dir(follow_symlinks=False):pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        try:yield Path(entry.path),entry.stat(follow_symlinks=False)
                        except FileNotFoundError:pass
        except FileNotFoundError:pass


def _publish_pointer(root, name):
    path=root.parent/(root.name+'-accounting.json')
    temporary=path.with_suffix('.json.part')
    with temporary.open('w') as handle:
        json.dump({'schema':1,'index':name},handle)
        handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,path)
    fd=os.open(root.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _index_path(root):
    pointer=root.parent/(root.name+'-accounting.json')
    try:
        saved=json.loads(pointer.read_text())
        name=saved['index']
        if (saved['schema']!=1 or not isinstance(name,str) or Path(name).name!=name
                or not name.startswith(root.name+'-accounting') or not name.endswith('.sqlite3')):
            raise ValueError('Invalid accounting generation')
        return root.parent/name
    except FileNotFoundError:
        # A lost pointer cannot establish that any previous generation is current.
        name=root.name+'-accounting-'+uuid.uuid4().hex+'.sqlite3'
        _publish_pointer(root,name)
        return root.parent/name
    except (ValueError,KeyError,TypeError):
        # A corrupt pointer cannot establish trust in any cached totals.
        os.replace(pointer,pointer.with_suffix('.'+uuid.uuid4().hex+'.corrupt'))
        name=root.name+'-accounting-'+uuid.uuid4().hex+'.sqlite3'
        _publish_pointer(root,name)
        return root.parent/name


def _corrupt(exc):
    return (getattr(exc,'sqlite_errorcode',0)&255) in (sqlite3.SQLITE_CORRUPT,sqlite3.SQLITE_NOTADB)


def _retire(root):
    old=_index_path(root)
    # Never rename/unlink an open WAL database. Other processes may retain idle
    # connections. Their eventual close must only checkpoint/delete OLD sidecars.
    old.with_suffix('.corrupt.json').write_text(json.dumps({'retained_index':old.name,'reason':'SQLite corruption'}))
    _publish_pointer(root,root.name+'-accounting-'+uuid.uuid4().hex+'.sqlite3')


def _connect(root):
    path=_index_path(root)
    db=sqlite3.connect(path,timeout=60)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript("""
            CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, dev INTEGER, ino INTEGER, size INTEGER);
            CREATE INDEX IF NOT EXISTS files_inode ON files(dev,ino);
            CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), dirty INTEGER,
                used INTEGER, results INTEGER, temporary INTEGER);
            INSERT OR IGNORE INTO state VALUES(1,1,0,0,0);
            CREATE TABLE IF NOT EXISTS cache_identity(id INTEGER PRIMARY KEY CHECK(id=1),dev INTEGER,ino INTEGER);
        """)
        generation=root.stat()
        identity=(generation.st_dev,generation.st_ino)
        if db.execute('SELECT dev,ino FROM cache_identity WHERE id=1').fetchone()!=identity:
            with db:
                db.execute('UPDATE state SET dirty=1')
                db.execute('INSERT OR REPLACE INTO cache_identity VALUES(1,?,?)',identity)
    except sqlite3.DatabaseError as exc:
        db.close()
        if not _corrupt(exc):raise
        _retire(root)
        return _connect(root)
    return db


def _totals(db,keys=None):
    where=''
    parameters=[]
    if keys is not None:
        if not keys:return (0,0,0)
        where=' WHERE '+ ' OR '.join('(dev=? AND ino=?)' for _ in keys)
        parameters=[x for pair in keys for x in pair]
    return db.execute('''SELECT COALESCE(SUM(size),0),COALESCE(SUM(result_size),0),COALESCE(SUM(temp_size),0)
        FROM (SELECT MAX(size) size,MAX(CASE WHEN path LIKE 'results/%' THEN size ELSE 0 END) result_size,
        MAX(CASE WHEN path LIKE '%.part' THEN size ELSE 0 END) temp_size FROM files'''+where+
        ' GROUP BY dev,ino)',parameters).fetchone()


def _rebuild(db,root):
    started=time.perf_counter()
    db.execute('UPDATE state SET dirty=1');db.commit()
    with db:
        db.execute('DELETE FROM files')
        db.executemany('INSERT INTO files VALUES(?,?,?,?)',
            ((str(p.relative_to(root)),s.st_dev,s.st_ino,s.st_size) for p,s in _walk(root)))
        db.execute('UPDATE state SET dirty=0,used=?,results=?,temporary=?',_totals(db))
    from app.services.planning_metrics import record
    record('cache_index_rebuild_calls',1)
    record('cache_index_rebuild_seconds',time.perf_counter()-started)


def _generation(root):
    index=_index_path(root)
    r=root.stat()
    try:
        s=index.stat()
        return os.getpid(),index.name,r.st_dev,r.st_ino,s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
    except FileNotFoundError:return None


def _connection(root):
    # WAL avoids rollback-journal fsyncs on every tiny metadata mutation. Keep a
    # bounded connection pool per IO thread so closing the last connection does
    # not force a WAL checkpoint for every observation. No quota counter is cached.
    pool=getattr(_local,'connections',None)
    if pool is None:pool=_local.connections=OrderedDict()
    entry=pool.pop(root,None)
    if entry is not None and entry[1]!=_generation(root):
        entry[0].close();entry=None
    db=entry[0] if entry is not None else _connect(root)
    pool[root]=(db,_generation(root))
    while len(pool)>8:
        _,old=pool.popitem(last=False);old[0].close()
    return db


@contextmanager
def _index(root, force_rebuild=False):
    root=Path(root).absolute();root.mkdir(parents=True,exist_ok=True)
    from app.services.satellite_cache import file_lock
    with file_lock(root/'quota.lock'):
        # Corruption in a data/index page may only surface during reconciliation,
        # after the schema and state page have already been read successfully.
        for attempt in range(2):
            db=_connection(root)
            try:
                if force_rebuild or db.execute('SELECT dirty FROM state').fetchone()[0]:_rebuild(db,root)
                break
            except sqlite3.DatabaseError as exc:
                _local.connections.pop(root,None);db.close()
                if not _corrupt(exc) or attempt:raise
                _retire(root)
        try:
            yield db,root
        except sqlite3.DatabaseError as exc:
            _local.connections.pop(root,None);db.close()
            if _corrupt(exc):_retire(root)
            raise
        finally:
            if root in _local.connections:
                _local.connections[root]=(db,_generation(root))


def usage(root):
    root=Path(root).absolute()
    active=getattr(_local,'active',None)
    if active is not None and active[1]==root:
        return active[0].execute('SELECT used,results,temporary FROM state').fetchone()
    started=time.perf_counter()
    with _index(root) as (db,_):
        from app.services.planning_metrics import record
        record('cache_index_read_calls',1)
        record('cache_index_read_seconds',time.perf_counter()-started)
        return db.execute('SELECT used,results,temporary FROM state').fetchone()


def rebuild(root):
    """Explicit maintenance after external imports/repairs, with all old writers stopped."""
    with _index(root,force_rebuild=True):pass


def _sync(db,root,scopes):
    names=set()
    entries={}
    for scope in scopes:
        p=Path(scope).absolute();relative=str(p.relative_to(root))
        # Exact files, plus descendants of explicitly scoped bundle directories.
        names.add(relative)
        names.update(row[0] for row in db.execute('SELECT path FROM files WHERE path=? OR (path>=? AND path<?)',
            (relative,relative+'/',relative+'/\uffff')))
        if p.is_symlink():continue
        if p.is_dir():
            for path,stat in _walk(p):entries[str(path.relative_to(root))]=stat
        elif p.exists():entries[relative]=p.stat()
    names.update(entries)
    keys=set((s.st_dev,s.st_ino) for s in entries.values())
    for name in names:
        keys.update(db.execute('SELECT dev,ino FROM files WHERE path=?',(name,)))
    # Chunking is unnecessary: one mutation scopes one bounded acquisition bundle.
    before=_totals(db,keys)
    db.executemany('DELETE FROM files WHERE path=?',((n,) for n in names))
    db.executemany('INSERT INTO files VALUES(?,?,?,?)',
        ((n,s.st_dev,s.st_ino,s.st_size) for n,s in entries.items()))
    after=_totals(db,keys)
    db.execute('UPDATE state SET used=used+?,results=results+?,temporary=temporary+?,dirty=0',
        tuple(a-b for a,b in zip(after,before)))


@contextmanager
def mutation(root, scopes, incoming=0, temporary=False, results=False):
    """Admit a conservative bound, journal, mutate, reconcile only touched paths.

    The global lock covers admission through reconciliation. No counter is kept in
    RAM. Exceptions reconcile surviving partial files; SIGKILL leaves dirty=1.
    Nested mutations are prohibited to keep reservation ownership explicit.
    """
    root=Path(root).absolute()
    if getattr(_local,'active',None) is not None:
        raise RuntimeError('Nested cache mutations are not permitted')
    scopes=[Path(p).absolute() for p in scopes]
    for p in scopes:
        p.relative_to(root)
        for ancestor in (p,*p.parents):
            if ancestor.is_symlink():raise ValueError('Cache mutation cannot traverse symlinks')
            if ancestor==root:break
    with _index(root) as (db,root):
        from app.services.satellite_cache import ensure_space
        from app.core.config import settings
        _local.active=(db,root)
        try:
            if incoming:
                ensure_space(root,incoming,temporary=temporary)
            if results and usage(root)[1]+incoming>settings.AFTERFIRE_ANALYSIS_RESULTS_MAX_GB*1024**3:
                raise ValueError('Derived raster results quota exceeded')
        finally:_local.active=None
        db.execute('UPDATE state SET dirty=1');db.commit()
        _local.active=(db,root)
        try:
            yield
        finally:
            try:
                # Persist directory entries before clearing the write-ahead bit.
                directories=set()
                for scope in scopes:
                    p=Path(scope).absolute()
                    p=p if p.is_dir() else p.parent
                    while p.is_relative_to(root):
                        if p.exists():directories.add(p)
                        if p==root:break
                        p=p.parent
                for directory in sorted(directories,key=lambda p:len(p.parts),reverse=True):
                    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                started=time.perf_counter()
                with db:_sync(db,root,scopes)
                from app.services.planning_metrics import record
                record('cache_index_sync_calls',1)
                record('cache_index_sync_seconds',time.perf_counter()-started)
            finally:_local.active=None


def atomic_json(path,value):
    import json
    from app.services.satellite_cache import cache_root
    data=json.dumps(value).encode();tmp=path.with_suffix(path.suffix+'.part')
    with mutation(cache_root(),[path,tmp],len(data)):
        try:
            with tmp.open('wb') as handle:
                handle.write(data);handle.flush();os.fsync(handle.fileno())
            os.replace(tmp,path)
        finally:tmp.unlink(missing_ok=True)
