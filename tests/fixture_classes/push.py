import re
from copy import deepcopy

from aiohttp.test_utils import TestClient

from em2 import Settings
from em2.comms import BasePusher
from em2.comms.http import create_app
from em2.comms.http.push import HttpDNSPusher
from em2.core import Action, Controller
from tests.conftest import test_store

from .authenicator import MockDNSResolver, SimpleAuthenticator


class Network:
    def __init__(self):
        self.nodes = {}

    def add_node(self, domain, controller):
        assert domain not in self.nodes
        self.nodes[domain] = controller


class SimplePusher(BasePusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.network = Network()

    async def ainit(self):
        await super().ainit()
        self.ds.data = test_store(self.settings.LOCAL_DOMAIN)

    async def push(self, action, event_id, data):
        new_action = Action(action.address, action.conv, action.verb, action.component,
                            item=action.item, timestamp=action.timestamp, event_id=event_id)
        prop_data = deepcopy(data)

        async with self.ds.connection() as conn:
            cds = self.ds.new_conv_ds(action.conv, conn)
            participants_data = await cds.receiving_participants()
            addresses = [p['address'] for p in participants_data]

        nodes = await self.get_nodes(*addresses)
        for ctrl in nodes:
            if ctrl != self.LOCAL:
                await ctrl.act(new_action, **prop_data)

    async def get_node(self, domain):
        return self.LOCAL if domain == self.settings.LOCAL_DOMAIN else self.network.nodes[domain]

    def __str__(self):
        return repr(self)


class CustomTestClient(TestClient):
    def __init__(self, app, domain):
        self.domain = domain
        self.regex = re.compile(r'https://em2\.{}(/.*)'.format(self.domain))
        super().__init__(app)

    def make_url(self, path):
        m = self.regex.match(path)
        assert m, (path, self.regex)
        sub_path = m.groups()[0]
        return self._server.make_url(sub_path)


def create_test_app(loop, domain='testapp.com'):
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore', LOCAL_DOMAIN=domain)
    ctrl = Controller(settings, loop=loop)
    auth = SimpleAuthenticator(settings=settings)
    auth._now_unix = lambda: 2461449600
    return create_app(ctrl, auth, loop=loop)


class HttpMockedDNSPusher(HttpDNSPusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0

    @property
    def resolver(self):
        return MockDNSResolver()

    def mx_query(self, host):
        self._mx_query_count += 1
        return super().mx_query(host)


class DoubleMockPusher(HttpMockedDNSPusher):
    """
    HttpDNSPusher with both dns and http mocked
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_client = None

    async def create_test_client(self, remote_domain='platform.remote.com'):
        self.app = create_test_app(self.loop, remote_domain)
        self.test_client = CustomTestClient(self.app, remote_domain)
        await self.test_client.start_server()

    @property
    def session(self):
        if not self.test_client:
            raise RuntimeError('test_client must be initialised with create_test_client before accessing session')
        return self.test_client

    def _now_unix(self):
        return 2461449600
