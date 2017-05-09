import psycopg2
import pytest
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from em2 import Settings
from em2.ds.pg.datastore import ConnectionContextManager, PostgresDataStore
from em2.ds.pg.models import Base
from em2.ds.pg.utils import get_dsn, pg_connect_kwargs

pg_settings = Settings(
    PG_DATABASE='em2_test',
    PG_POOL_MAXSIZE=4,
    PG_POOL_TIMEOUT=5,
)


@pytest.fixture(scope='session')
def dsn():
    return get_dsn(pg_settings)


@pytest.yield_fixture(scope='session')
def db(dsn):
    conn = psycopg2.connect(**pg_connect_kwargs(pg_settings))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS {}'.format(pg_settings.PG_DATABASE))
    cur.execute('CREATE DATABASE {}'.format(pg_settings.PG_DATABASE))

    engine = sa_create_engine(dsn)
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()
    cur.execute('DROP DATABASE {}'.format(pg_settings.PG_DATABASE))
    cur.close()
    conn.close()


@pytest.yield_fixture
def Session(db):
    connection = db.connect()
    transaction = connection.begin()

    session_factory = sessionmaker(bind=db)
    _Session = scoped_session(session_factory)
    yield _Session

    transaction.rollback()
    connection.close()
    _Session.remove()


@pytest.yield_fixture
def empty_db(Session):
    yield

    session = Session()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()


class TestPostgresDataStore(PostgresDataStore):
    _conn_ctx = None

    def conn_manager(self):
        # force the same connection to be used each time
        self._conn_ctx = self._conn_ctx or TestCtx(self.engine)
        return self._conn_ctx

    async def terminate(self):
        if self._conn_ctx is not None:
            await self._conn_ctx.terminate()
        if self.engine is not None:
            self.engine.close()
            await self.engine.wait_closed()


class TestCtx(ConnectionContextManager):
    conn = None

    async def __aenter__(self):
        if self.conn is None:
            self.conn = await self._engine._acquire()
            self.tr = await self.conn._begin()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def terminate(self):
        await self.tr.rollback()
        self.tr = None
        self._engine.release(self.conn)
        self.conn = None


@pytest.yield_fixture
def pg_conn():
    settings = Settings(
        PG_DATABASE='test_prepare_database',
        DATASTORE_CLS='em2.ds.pg.datastore.PostgresDataStore',
    )
    conn = psycopg2.connect(**pg_connect_kwargs(settings))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS {}'.format(settings.PG_DATABASE))

    yield settings, cur

    cur.execute('DROP DATABASE IF EXISTS {}'.format(settings.PG_DATABASE))
    cur.close()
    conn.close()