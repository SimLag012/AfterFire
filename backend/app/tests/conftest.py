"""Never run destructive test fixtures against the user's archive database."""
import atexit
import os
import shutil
import tempfile

_test_directory = tempfile.mkdtemp(prefix='afterfire-tests-')
_postgres_test_url = os.environ.get('AF_TEST_DATABASE_URL')
if _postgres_test_url:
    from sqlalchemy.engine import make_url
    assert make_url(_postgres_test_url).database.startswith('afterfire_test_'), 'Refusing a non-test PostgreSQL database'
    os.environ['DATABASE_URL'] = _postgres_test_url
else:
    os.environ['DATABASE_URL'] = f'sqlite+aiosqlite:///{_test_directory}/tests.db'
# Provider unit tests opt in explicitly; never inherit the deployment's live credentials.
os.environ['FIRMS_MAP_KEY'] = ''
os.environ['AFTERFIRE_EARTH_ENGINE_ENABLED'] = 'false'
os.environ['AFTERFIRE_EE_PROJECT_ID'] = ''
os.environ['AFTERFIRE_SATELLITE_PROVIDER'] = 'auto'
for _credential in ('EARTHDATA_USERNAME', 'EARTHDATA_PASSWORD', 'EARTHDATA_TOKEN', 'LLM_API_KEY'):
    os.environ[_credential] = ''
os.environ['AFTERFIRE_APPEEARS_ENABLED'] = 'false'
# A dedicated database is insufficient isolation: cache tests must not inherit
# the deployment's retained sources or published raster directory either.
os.environ['AFTERFIRE_ANALYSIS_CACHE_DIR'] = os.path.join(_test_directory, 'satellite')
from pathlib import Path
from app.core.config import Settings
Settings.cache_dir = property(lambda self: Path(_test_directory) / 'provider-cache')
atexit.register(shutil.rmtree, _test_directory, ignore_errors=True)


import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def dispose_test_connection_pool():
    yield
    # pytest-asyncio gives each test its own loop; asyncpg pools cannot cross loops.
    from app.db.database import engine
    await engine.dispose()


import asyncio
import pytest


@pytest.fixture(scope='session', autouse=True)
def reset_explicit_postgres_test_schema():
    if not _postgres_test_url:
        return
    from app.db.database import Base, engine
    assert engine.url.database.startswith('afterfire_test_')
    async def reset():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()
    asyncio.run(reset())
