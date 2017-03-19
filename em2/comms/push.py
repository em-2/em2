import base64
import logging
from typing import Set

from arq import concurrent
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from em2 import Settings
from em2.core import Action
from em2.utils import now_unix_secs

from .redis_dns import RedisDNSActor

logger = logging.getLogger('em2.push')


class Pusher(RedisDNSActor):
    """
    Pushers are responsible for distributing data to other platforms and also for prompting the distribution of
    data to addresses which do not support em2, eg. to SMTP addresses.

    To do this Pushers should keep track of the distinct platforms involved in each conversation,
    but also keep a complete list of participants to be included (eg. cc'd in SMTP) in fallback.
    """
    LOCAL = 'L'
    B_LOCAL = LOCAL.encode()
    FALLBACK = 'F'

    # prefix for hashes of address domain -> node (platform) domain
    domain_node_prefix = b'dn:'
    # prefix for strings containing auth tokens foreach node
    auth_token_prefix = b'ak:'

    def __init__(self, settings: Settings, *, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop
        self.fallback = settings.fallback_cls(settings, loop=loop)
        logger.info('initialising pusher %s, ds: %s', self, self.settings.datastore_cls.__name__)
        self._early_token_expiry = self.settings.COMMS_PUSH_TOKEN_EARLY_EXPIRY
        self.ds = None
        super().__init__(**kwargs)

    async def startup(self):
        assert self.ds is None, 'datastore already initialised'
        if self._concurrency_enabled:
            assert self.is_shadow, 'datastore should only be initialised for the pusher in shadow mode'
        self.ds = self.settings.datastore_cls(settings=self.settings, loop=self.loop)
        await self.ds.startup()
        await self.fallback.startup()

    async def shutdown(self):
        await self.ds.shutdown()
        await self.fallback.shutdown()

    async def push(self, action, data):
        await self._send(action.to_dict(), data)

    @concurrent
    async def _send(self, action_dict, data):
        action = Action(**action_dict)
        async with self.ds.conn_manager() as conn:
            cds = self.ds.new_conv_ds(action.conv, conn)

            participants_data = await cds.receiving_participants()
            addresses = [p['address'] for p in participants_data]
            nodes = await self.get_nodes(*addresses)
            remote_em2_nodes = [n for n in nodes if n not in {self.LOCAL, self.FALLBACK}]

            logger.info('%s %.6s to %d parts on %d nodes, of which em2 %d', action.verb, action.conv,
                        len(participants_data), len(nodes), len(remote_em2_nodes))
            await self._push_em2(remote_em2_nodes, action, data)
            if any(n for n in nodes if n == self.FALLBACK):
                logger.info('%s %.6s fallback required', action.verb, action.conv)
                # some actions eg. publish already include subject
                subject = data.get('subject') or await cds.get_subject()
                await self.fallback.push(action, data, participants_data, subject)
            # TODO update event with success or failure

    async def _push_em2(self, nodes, action, data):
        raise NotImplementedError()

    def get_domain(self, address):
        """
        Parse an address and return its domain.
        """
        return address[address.index('@') + 1:]

    async def get_node(self, domain: str) -> str:
        """
        Find the node for a given participant in a conversation.

        :param domain: domain to find node for
        :return: node's domain or None if em2 is not enabled for this address
        """
        raise NotImplementedError()

    async def get_nodes(self, *addresses: str) -> Set[str]:
        # cache here instead of in get_node so we can use the same redis connection
        nodes = set()
        checked_domains = set()
        async with await self.get_redis_conn() as redis:
            for address in addresses:
                d = self.get_domain(address)
                if d in checked_domains:
                    continue
                checked_domains.add(d)

                key = self.domain_node_prefix + d.encode()
                node_b = await redis.get(key)
                if node_b:
                    node = node_b.decode()
                    logger.info('found cached node %s -> %s', d, node)
                else:
                    node = await self.get_node(d)
                    logger.info('got node for %s -> %s', d, node)
                    await redis.setex(key, self.settings.COMMS_DNS_CACHE_EXPIRY, node.encode())
                nodes.add(node)
        return nodes

    def get_auth_data(self):
        timestamp = self._now_unix()
        msg = '{}:{}'.format(self.settings.LOCAL_DOMAIN, timestamp)
        h = SHA256.new(msg.encode())

        key = RSA.importKey(self.settings.private_domain_key)
        signer = PKCS1_v1_5.new(key)
        signature = base64.urlsafe_b64encode(signer.sign(h)).decode()
        return {
            'platform': self.settings.LOCAL_DOMAIN,
            'timestamp': timestamp,
            'signature': signature,
        }

    async def authenticate(self, node_domain: str) -> str:
        logger.debug('authenticating with %s', node_domain)
        token_key = self.auth_token_prefix + node_domain.encode()
        async with await self.get_redis_conn() as redis:
            token = await redis.get(token_key)
            if token:
                token = token.decode()
            else:
                token = await self._authenticate_direct(node_domain)
                _, expires_at, _ = token.split(':', 2)
                expire_token_at = int(expires_at) - self._early_token_expiry
                await self.set_exat(redis, token_key, token, expire_token_at)
        logger.info('successfully authenticated with %s', node_domain)
        return token

    async def _authenticate_direct(self, node_domain):
        raise NotImplementedError()

    def _now_unix(self):
        return now_unix_secs()

    def __repr__(self):
        return '{}<{}>'.format(self.__class__.__name__, self.settings.LOCAL_DOMAIN)


class NullPusher(Pusher):  # pragma: no cover
    """
    Pusher with no functionality to connect to other platforms. Used for testing or trial purposes only.
    """
    async def push(self, action, data):
        pass

    async def get_node(self, domain):
        pass

    async def authenticate(self, node_domain: str):
        pass
