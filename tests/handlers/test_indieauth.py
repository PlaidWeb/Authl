""" Tests of the IndieAuth handler """
# pylint:disable=missing-docstring,duplicate-code


import json
import logging

import pytest
import requests
from bs4 import BeautifulSoup

from authl import disposition, tokens
from authl.handlers import indieauth

from . import parse_args

LOGGER = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def purge_endpoint_cache():
    # pylint:disable=protected-access
    indieauth._ENDPOINT_CACHE.clear()


def test_find_endpoint_by_url(requests_mock):
    from authl.handlers.indieauth import find_endpoint, find_endpoints
    requests_mock.get('http://link.absolute/', text='Nothing to see',
                      headers={'Link': '<https://endpoint/>; rel="authorization_endpoint",' +
                               '<https://token/>; rel="token_endpoint"'}
                      )

    assert find_endpoints('http://link.absolute/')[0] == {
        'authorization_endpoint': 'https://endpoint/',
        'token_endpoint': 'https://token/'
    }
    assert find_endpoint('http://link.absolute/')[0] == 'https://endpoint/'
    assert find_endpoint('http://link.absolute/', rel='token_endpoint')[0] == 'https://token/'

    requests_mock.get('http://link.relative/', text='Nothing to see',
                      headers={'Link': '<invalid>; rel="authorization_endpoint"'})
    assert find_endpoint('http://link.relative/')[0] == 'invalid'

    requests_mock.get('http://content.absolute/',
                      text='<link rel="authorization_endpoint" href="https://endpoint/">')
    assert find_endpoint(
        'http://content.absolute/')[0] == 'https://endpoint/'

    requests_mock.get('http://content.relative/',
                      text='<link rel="authorization_endpoint" href="endpoint" >')
    assert find_endpoint(
        'http://content.relative/')[0] == 'http://content.relative/endpoint'

    requests_mock.get('http://both/',
                      text='''<link rel="authorization_endpoint" href="http://content/endpoint">
                      <link rel="token_endpoint" href="http://content/token">
                      <link rel="ticket_endpoint" href="/content/ticket">''',
                      headers={'Link': '<https://header/endpoint/>; rel="authorization_endpoint"'}
                      )
    assert find_endpoints('http://both/')[0] == {
        'authorization_endpoint': 'https://header/endpoint/',
        'token_endpoint': 'http://content/token',
        'ticket_endpoint': 'http://both/content/ticket'
    }

    requests_mock.get('http://nothing/', text='nothing')
    assert not find_endpoints('http://nothing/')[0]

    assert not find_endpoints('https://undefined.example')[0]

    # test the caching
    requests_mock.reset()
    assert find_endpoints('http://link.absolute/')[0] == {
        'authorization_endpoint': 'https://endpoint/',
        'token_endpoint': 'https://token/'
    }
    assert find_endpoints('http://link.relative/')[0]['authorization_endpoint'] == 'invalid'
    assert find_endpoint(
        'http://content.absolute/')[0] == 'https://endpoint/'
    assert find_endpoint(
        'http://content.relative/')[0] == 'http://content.relative/endpoint'
    assert not requests_mock.called

    # but a failed lookup shouldn't be cached
    assert not find_endpoints('http://nothing/')[0]
    assert requests_mock.called


def test_find_endpoint_redirections(requests_mock):
    from authl.handlers.indieauth import find_endpoints
    # test that redirections get handled correctly
    requests_mock.get('http://start/', status_code=301,
                      headers={'Location': 'http://perm-redirect/'})
    requests_mock.get('http://perm-redirect/', status_code=302,
                      headers={'Location': 'http://temp-redirect/'})
    requests_mock.get('http://temp-redirect/',
                      text='<link rel="authorization_endpoint" href="https://foobar/">')

    # final URL should be the last permanent redirection
    assert find_endpoints('http://start/') == ({'authorization_endpoint': 'https://foobar/'},
                                               'http://perm-redirect/')
    assert requests_mock.call_count == 3

    # endpoint should be cached for both the initial and permanent-redirect URLs
    assert find_endpoints('http://start/') == ({'authorization_endpoint': 'https://foobar/'},
                                               'http://perm-redirect/')
    assert find_endpoints(
        'http://perm-redirect/') == ({'authorization_endpoint': 'https://foobar/'},
                                     'http://perm-redirect/')
    assert requests_mock.call_count == 3


def test_find_endpoint_by_content(requests_mock):
    from authl.handlers.indieauth import find_endpoint, find_endpoints

    links = {'authorization_endpoint': {'url': 'http://link_endpoint'}}
    rel_content = BeautifulSoup('<link rel="authorization_endpoint" href="foo">',
                                'html.parser')
    abs_content = BeautifulSoup('<link rel="authorization_endpoint" href="http://foo/">',
                                'html.parser')

    assert find_endpoints(
        'http://example', links=links)[0] == {'authorization_endpoint': 'http://link_endpoint'}
    assert find_endpoint('http://example',
                         content=rel_content)[0] == 'http://example/foo'
    assert find_endpoint(
        'http://example', content=abs_content)[0] == 'http://foo/'

    # link header overrules page content
    assert find_endpoint('http://example',
                         links=links,
                         content=rel_content)[0] == 'http://link_endpoint'

    # final result should be cached
    assert find_endpoints('http://example')[0] == {'authorization_endpoint': 'http://link_endpoint'}

    assert not requests_mock.called


def test_verify_id(requests_mock):
    endpoint_1 = {'Link': '<https://auth.example/1>; rel="authorization_endpoint'}
    endpoint_2 = {'Link': '<https://auth.example/2>; rel="authorization_endpoint'}

    # Same URL is always allowed
    assert indieauth.verify_id('https://matching.example',
                               'https://matching.example') == 'https://matching.example'

    # Different URL is allowed as long as the endpoints match
    requests_mock.get('https://different.example/1', headers=endpoint_1)
    requests_mock.get('https://different.example/2', headers=endpoint_1)
    assert indieauth.verify_id('https://different.example/1',
                               'https://different.example/2') == 'https://different.example/2'

    # Different domain is allowed as long as the endpoints match
    requests_mock.get('https://different.domain/1', headers=endpoint_1)
    assert indieauth.verify_id('https://different.example/1',
                               'https://different.domain/1') == 'https://different.domain/1'

    # Don't allow if the endpoints mismatch, even if the domain matches
    requests_mock.get('https://same.example/alice', headers=endpoint_1)
    requests_mock.get('https://same.example/bob', headers=endpoint_2)
    with pytest.raises(ValueError):
        indieauth.verify_id('https://same.example/alice', 'https://same.example/bob')

    # scheme change is allowed as long as the endpoint stays the same
    requests_mock.get('http://upgrade.example', headers=endpoint_2)
    requests_mock.get('https://upgrade.example', headers=endpoint_2)
    assert indieauth.verify_id('http://upgrade.example', 'https://upgrade.example')

    # redirect is fine as long as the final endpoint matches
    requests_mock.get('https://redir.example/user', headers=endpoint_1)
    requests_mock.get('https://redir.example/perm', status_code=301,
                      headers={'Location': 'https://redir.example/target'})
    requests_mock.get('https://redir.example/temp', status_code=302,
                      headers={'Location': 'https://redir.example/target'})
    requests_mock.get('https://redir.example/target', headers=endpoint_1)
    assert indieauth.verify_id('https://redir.example/user',
                               'https://redir.example/perm') == 'https://redir.example/target'
    assert indieauth.verify_id('https://redir.example/user',
                               'https://redir.example/temp') == 'https://redir.example/temp'

    # Target page must have an endpoint
    requests_mock.get('https://missing.example/src', headers=endpoint_1)
    requests_mock.get('https://missing.example/dest', text='foo')
    with pytest.raises(ValueError):
        indieauth.verify_id('https://matching.example/src', 'https://missing.example/dest')


def test_handler_success(requests_mock):
    store = {}
    handler = indieauth.IndieAuth('http://client/', tokens.DictStore(store))

    assert handler.service_name == 'IndieAuth'
    assert handler.url_schemes
    assert 'IndieAuth' in handler.description
    assert handler.cb_id
    assert handler.logo_html[0][1] == 'IndieAuth'

    # profile page at http://example.user/ which redirects to https://example.user/bob
    endpoint = {'Link': '<https://auth.example/endpoint>; rel="authorization_endpoint'}
    requests_mock.get('http://example.user/', headers=endpoint)
    requests_mock.get('https://example.user/bob', headers=endpoint)

    injected = requests.get('http://example.user/')

    # it should not handle the URL on its own
    assert not handler.handles_url('http://example.user/')
    assert handler.handles_page('http://example.user/', injected.headers,
                                BeautifulSoup(injected.text, 'html.parser'),
                                injected.links)

    # and now the URL should be cached
    assert handler.handles_url('http://example.user/')

    disp = handler.initiate_auth('http://example.user/', 'http://client/cb', '/dest')
    assert isinstance(disp, disposition.Redirect)
    assert disp.url.startswith('https://auth.example/endpoint')

    # fake the user dialog on the IndieAuth endpoint
    user_get = parse_args(disp.url)
    assert user_get['redirect_uri'].startswith('http://client/cb')
    assert 'client_id' in user_get
    assert 'state' in user_get
    assert user_get['state'] in store
    assert user_get['response_type'] == 'code'
    assert 'me' in user_get

    # fake the verification response
    def verify_callback(request, _):
        import urllib.parse
        args = urllib.parse.parse_qs(request.text)
        assert args['code'] == ['asdf']
        assert args['client_id'] == ['http://client/']
        assert 'redirect_uri' in args
        return json.dumps({
            'me': 'https://example.user/bob'
        })
    requests_mock.post('https://auth.example/endpoint', text=verify_callback)

    LOGGER.debug("state=%s", user_get['state'])
    response = handler.check_callback(
        user_get['redirect_uri'],
        {
            'state': user_get['state'],
            'code': 'asdf',
        },
        {})
    LOGGER.debug("verification response: %s", response)
    assert isinstance(response, disposition.Verified)
    assert response.identity == 'https://example.user/bob'
    assert response.redir == '/dest'

    # trying to replay the same transaction should fail
    response = handler.check_callback(
        user_get['redirect_uri'],
        {
            'state': user_get['state'],
            'code': 'asdf',
        },
        {})
    assert isinstance(response, disposition.Error)


def test_handler_failures(requests_mock):
    store = {}
    handler = indieauth.IndieAuth('http://client/', tokens.DictStore(store), 10)

    # Attempt to auth against page with no endpoint
    requests_mock.get('http://no-endpoint/', text='hello')
    response = handler.initiate_auth('http://no-endpoint/', 'http://cb/', 'bogus')
    assert isinstance(response, disposition.Error)
    assert 'endpoint' in response.message
    assert len(store) == 0

    # Attempt to inject a transaction-less callback response
    response = handler.check_callback('http://no-transaction', {}, {})
    assert isinstance(response, disposition.Error)
    assert 'No transaction' in response.message
    assert len(store) == 0

    # Attempt to inject a forged callback response
    response = handler.check_callback('http://bogus-transaction', {'state': 'bogus'}, {})
    assert isinstance(response, disposition.Error)
    assert 'Invalid token' in response.message
    assert len(store) == 0

    # Get a valid state token
    requests_mock.get('http://example.user/',
                      text='hello',
                      headers={'Link': '<http://endpoint/>; rel="authorization_endpoint"'})

    response = handler.initiate_auth('http://example.user', 'http://client/cb', '/dest')
    assert isinstance(response, disposition.Redirect)
    data = {'state': parse_args(response.url)['state']}
    assert len(store) == 1

    # no code assigned
    assert "Missing 'code'" in handler.check_callback('http://client/cb', data, {}).message
    assert len(store) == 0

    def check_failure(message):
        assert len(store) == 0
        response = handler.initiate_auth('http://example.user', 'http://client/cb', '/dest')
        assert isinstance(response, disposition.Redirect)
        assert len(store) == 1
        data = {
            'state': parse_args(response.url)['state'],
            'code': 'bogus'
        }
        response = handler.check_callback('http://client/cb', data, {})
        assert isinstance(response, disposition.Error)
        assert message in response.message
        assert len(store) == 0

    # callback returns error
    requests_mock.post('http://endpoint/', status_code=400)
    check_failure('returned 400')

    # callback returns broken JSON
    requests_mock.post('http://endpoint/', text='invalid json')
    check_failure('invalid response JSON')

    # callback returns a page with no endpoint
    requests_mock.post('http://endpoint/', json={'me': 'http://empty.user'})
    requests_mock.get('http://empty.user', text='hello')
    check_failure('missing IndieAuth endpoint')

    # callback returns a page with a different endpoint
    requests_mock.post('http://endpoint/', json={'me': 'http://different.user'})
    requests_mock.get('http://different.user',
                      headers={'Link': '<http://otherendpoint/>; rel="authorization_endpoint"'})
    check_failure('Authorization endpoint mismatch')


def test_login_timeout(mocker, requests_mock):
    store = {}
    handler = indieauth.IndieAuth('http://client/', tokens.DictStore(store), 10)

    mock_time = mocker.patch('time.time')
    mock_time.return_value = 238742

    requests_mock.get('http://example.user/',
                      text='hello',
                      headers={'Link': '<http://endpoint/>; rel="authorization_endpoint"'})

    assert len(store) == 0
    response = handler.initiate_auth('http://example.user', 'http://client/cb', '/dest')
    assert isinstance(response, disposition.Redirect)
    assert len(store) == 1

    mock_time.return_value += 100

    data = {'state': parse_args(response.url)['state'], 'code': 'bogus'}
    response = handler.check_callback('http://client/cb', data, {})
    assert isinstance(response, disposition.Error)
    assert 'timed out' in response.message
    assert len(store) == 0


def test_from_config():
    # pylint:disable=protected-access
    handler = indieauth.from_config({'INDIEAUTH_CLIENT_ID': 'poiu',
                                     'INDIEAUTH_PENDING_TTL': 12345}, "plop")
    assert isinstance(handler, indieauth.IndieAuth)
    assert handler._client_id == 'poiu'
    assert handler._timeout == 12345
    assert handler._token_store == "plop"


def test_get_profile(requests_mock):
    profile_html = r"""
    <link rel="authorization_endpoint" href="https://endpoint.example/">
    <div class="h-card">
    <a class="u-url p-name" href="https://example.foo/~user/">larry</a>
    <p class="e-note">I'm <em>Larry</em>. And you're not. <span class="p-pronouns">he/him</span> or
    <span class="p-pronoun">whatever</span></p>
    <a class="u-email" href="mailto:larry%40example.foo">larry at example dot foo</a>
    <img class="u-photo" src="plop.jpg">
    </div>"""

    profile_blob = {
        'avatar': "http://profile.example/plop.jpg",
        'bio': "I'm Larry. And you're not. he/him or whatever",
        'email': "larry@example.foo",
        'name': "larry",
        'pronouns': "he/him",
        'homepage': "https://example.foo/~user/",
        'endpoints': {
            'authorization_endpoint': 'https://endpoint.example/',
        },
    }

    # test basic parsing
    profile_mock = requests_mock.get('http://profile.example', text=profile_html)
    profile = indieauth.get_profile('http://profile.example')
    assert profile_mock.call_count == 1

    assert profile == profile_blob

    # test cache prefill
    profile_mock = requests_mock.get('https://cached.example', text=profile_html)

    handler = indieauth.from_config({'INDIEAUTH_CLIENT_ID': 'poiu',
                                     'INDIEAUTH_PENDING_TTL': 12345}, "plop")

    assert not handler.handles_url('https://cached.example')

    injected = requests.get('https://cached.example')
    assert handler.handles_page('https://cached.example', injected.headers,
                                BeautifulSoup(injected.text, 'html.parser'),
                                injected.links)
    assert profile_mock.call_count == 1

    indieauth.get_profile('https://cached.example')
    assert profile_mock.call_count == 1
    assert profile == profile_blob


def test_profile_partial(requests_mock):
    profile_html = r"""
    <div class="h-card">
    <a class="u-url" href="https://example.foo/~user/">larry</a>
    <p class="e-note">I'm <em>Larry</em>. And you're not.</p>
    <a class="u-email" href="mailto:larry%40example.foo">larry at example dot foo</a>
    </div><div class="h-card">
    <a class="u-email" href="mailto:notme@example.com"></a>
    </div>
    """

    profile_blob = {
        'homepage': 'https://example.foo/~user/',
        'bio': "I'm Larry. And you're not.",
        'email': 'larry@example.foo',
    }

    requests_mock.get('https://partial.example', text=profile_html)
    profile = indieauth.get_profile('https://partial.example')
    assert profile == profile_blob
