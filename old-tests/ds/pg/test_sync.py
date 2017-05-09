import asyncio
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from em2.core import Action, Controller, Retrieval, RVerbs, Verbs
from em2.ds.pg.models import Conversation
from em2.ds.pg.utils import prepare_database

slow = pytest.mark.skipif(pytest.config.getoption('--fast'), reason='not run with --fast flag')


def test_create_retrieve_conversation(Session):
    session = Session()
    assert session.query(Conversation).count() == 0
    con = Conversation(
        conv_id='x',
        creator='user@example.com',
        subject='testing',
        ref='testing',
        timestamp=datetime.datetime.now(),
        status='draft',
    )
    assert session.query(Conversation).count() == 0
    session.add(con)
    assert session.query(Conversation).count() == 1


def test_create_conversation_duplicate_id(Session):
    session = Session()
    assert session.query(Conversation).count() == 0
    con1 = Conversation(
        conv_id='x',
        creator='user@example.com',
        subject='testing',
        ref='testing',
        timestamp=datetime.datetime.now(),
        status='draft',
    )
    session.add(con1)
    assert session.query(Conversation).count() == 1
    con2 = Conversation(
        conv_id='x',
        creator='user2@example.com',
        subject='testing',
        ref='testing',
        timestamp=datetime.datetime.now(),
        status='draft',
    )
    session.add(con2)
    with pytest.raises(IntegrityError):
        session.flush()


@slow
def test_prepare_database(pg_conn):
    settings, cur = pg_conn
    cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', (settings.PG_DATABASE,))
    assert cur.fetchone()[0] is False

    loop = asyncio.new_event_loop()

    def count_convs(_ctrl):
        retrieval = Retrieval('testing@example.com', verb=RVerbs.LIST)
        return len(loop.run_until_complete(_ctrl.retrieve(retrieval)))

    assert prepare_database(settings, delete_existing=False) is True

    cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', (settings.PG_DATABASE,))
    assert cur.fetchone()[0] is True

    ctrl = Controller(settings=settings, loop=loop)
    loop.run_until_complete(ctrl.startup())
    loop.run_until_complete(ctrl.act(Action('testing@example.com', None, Verbs.ADD), subject='first conversation'))
    assert count_convs(ctrl) == 1
    loop.run_until_complete(ctrl.ds.shutdown())

    assert prepare_database(settings, delete_existing=False) is False

    # check conversation still exists as we haven't recreated the database
    ctrl = Controller(settings=settings, loop=loop)
    loop.run_until_complete(ctrl.startup())
    assert count_convs(ctrl) == 1
    loop.run_until_complete(ctrl.ds.shutdown())

    assert prepare_database(settings, delete_existing=True) is True

    # check conversation doesn't exists as we have recreated the database
    ctrl = Controller(settings=settings, loop=loop)
    loop.run_until_complete(ctrl.startup())
    assert count_convs(ctrl) == 0
    loop.run_until_complete(ctrl.ds.shutdown())