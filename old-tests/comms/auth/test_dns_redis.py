import pytest

from em2 import Settings
from em2.comms import RedisDNSAuthenticator
from em2.exceptions import FailedInboundAuthentication
from tests.fixture_classes import INTERNET_CONNECTED, PLATFORM, TIMESTAMP, VALID_SIGNATURE, RedisMockDNSAuthenticator


@pytest.fixture
def redis_auth(get_redis_pool, loop):
    settings = Settings(R_DATABASE=2)
    auth = None

    async def setup(auth_class=RedisDNSAuthenticator):
        nonlocal auth
        auth = auth_class(settings=settings, loop=loop)
        auth._redis_pool = await get_redis_pool()
        return auth

    return setup


async def test_key_set_get(redis_auth):
    auth = await redis_auth()
    expireat = auth._now_unix() + 100
    await auth._store_platform_token('testing', expireat)
    assert await auth.key_exists('testing') is True
    async with auth._redis_pool.get() as redis:
        assert 99 <= await redis.ttl('testing') <= 100


async def test_key_set_get_missing(redis_auth):
    auth = await redis_auth()
    assert await auth.key_exists('other') is False


async def test_key_verification(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    auth._now_unix = lambda: 2461449600

    platform_key = await auth.authenticate_platform(PLATFORM, TIMESTAMP, VALID_SIGNATURE)
    await auth.valid_platform_token(platform_key)


async def test_key_verification_missing_dns(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    auth._now_unix = lambda: 2461449600

    with pytest.raises(FailedInboundAuthentication) as excinfo:
        await auth.authenticate_platform('notfoobar.com', 2461449600, VALID_SIGNATURE)
    assert excinfo.value.args[0] == 'no "em2key" TXT dns record found'


async def test_key_verification_bad_em2key(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    auth._now_unix = lambda: 2461449600

    with pytest.raises(FailedInboundAuthentication) as excinfo:
        await auth.authenticate_platform('badkey.com', 2461449600, VALID_SIGNATURE)
    assert excinfo.value.args[0] == 'no "em2key" TXT dns record found'


async def test_check_domain_platform_cache(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    assert await auth._check_domain_uses_platform('whatever.com', 'whoever.com') is None
    async with auth._redis_pool.get() as redis:
        await redis.set(b'pl:whatever.com', b'whoever.com')
    assert await auth._check_domain_uses_platform('whatever.com', 'whoever.com') is True


async def test_check_domain_platform_mx_match(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    assert await auth._check_domain_uses_platform('whatever.com', 'em2.platform.whatever.com') is True
    async with auth._redis_pool.get() as redis:
        await redis.get('pl:whatever.com') == 'em2.platform.whatever.com'


@pytest.mark.skipif(not INTERNET_CONNECTED, reason='no internet connection')
async def test_mx_lookup(redis_auth):
    auth = await redis_auth()
    r = auth.resolver
    results = await r.query('gmail.com', 'MX')
    assert results[0].host.endswith('google.com')
    # check we get back the same resolver each time
    assert id(r) == id(auth._resolver)


async def test_mx_lookup_dns_error(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    results = await auth.mx_query('good.com')
    assert results == [(5, 'em2.platform.good.com'), (10, 'mx.platform.good.com')]
    results = await auth.mx_query('dns_error.com')
    assert results == []