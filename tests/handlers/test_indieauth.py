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
    from authl.handlers.indieauth import find_endpoint
    requests_mock.get('http://link.absolute/', text='Nothing to see',
                      headers={'Link': '<https://endpoint/>; rel="authorization_endpoint"'})

    assert find_endpoint('http://link.absolute/') == 'https://endpoint/'

    requests_mock.get('http://link.relative/', text='Nothing to see',
                      headers={'Link': '<invalid>; rel="authorization_endpoint"'})
    assert find_endpoint('http://link.relative/') == 'invalid'

    requests_mock.get('http://content.absolute/',
                      text='<link rel="authorization_endpoint" href="https://endpoint/">')
    assert find_endpoint('http://content.absolute/') == 'https://endpoint/'

    requests_mock.get('http://content.relative/',
                      text='<link rel="authorization_endpoint" href="endpoint" >')
    assert find_endpoint('http://content.relative/') == 'http://content.relative/endpoint'

    requests_mock.get('http://both/',
                      text='<link rel="authorization_endpoint" href="http://content/endpoint">',
                      headers={'Link': '<https://header/endpoint/>; rel="authorization_endpoint"'}
                      )
    assert find_endpoint('http://both/') == 'https://header/endpoint/'

    requests_mock.get('http://nothing/', text='nothing')
    assert find_endpoint('http://nothing/') is None

    assert find_endpoint('https://undefined.example') is None

    # test the caching
    requests_mock.reset()
    assert find_endpoint('http://link.absolute/') == 'https://endpoint/'
    assert find_endpoint('http://link.relative/') == 'invalid'
    assert find_endpoint('http://content.absolute/') == 'https://endpoint/'
    assert find_endpoint('http://content.relative/') == 'http://content.relative/endpoint'
    assert not requests_mock.called

    # but a failed lookup shouldn't be cached
    assert find_endpoint('http://nothing/') is None
    assert requests_mock.called


def test_find_endpoint_by_content(requests_mock):
    links = {'authorization_endpoint': {'url': 'http://link_endpoint'}}
    rel_content = BeautifulSoup('<link rel="authorization_endpoint" href="foo">',
                                'html.parser')
    abs_content = BeautifulSoup('<link rel="authorization_endpoint" href="http://foo/">',
                                'html.parser')

    assert indieauth.find_endpoint('http://example', links=links) == 'http://link_endpoint'
    assert indieauth.find_endpoint('http://example',
                                   content=rel_content) == 'http://example/foo'
    assert indieauth.find_endpoint('http://example', content=abs_content) == 'http://foo/'

    # link header overrules page content
    assert indieauth.find_endpoint('http://example',
                                   links=links,
                                   content=rel_content) == 'http://link_endpoint'

    assert not requests_mock.called


def test_verify_id(requests_mock):
    endpoint_1 = {'Link': '<https://auth.example/1>; rel="authorization_endpoint'}
    endpoint_2 = {'Link': '<https://auth.example/2>; rel="authorization_endpoint'}

    # Same URL is always allowed
    assert indieauth.verify_id('https://matching.example',
                               'https://matching.example') == 'https://matching.example'

    # Different URL is allowed as long as the domain and endpoint match
    requests_mock.get('https://different.example/1', headers=endpoint_1)
    requests_mock.get('https://different.example/2', headers=endpoint_1)
    assert indieauth.verify_id('https://different.example/1',
                               'https://different.example/2') == 'https://different.example/2'

    # Don't allow if the domain doesn't match, even if the endpoint does
    requests_mock.get('https://one.example', headers=endpoint_1)
    requests_mock.get('https://two.example', headers=endpoint_1)
    with pytest.raises(ValueError):
        indieauth.verify_id('https://one.example', 'https://two.example')

    # Don't allow if the endpoints mismatch, even if the domain matches
    requests_mock.get('https://same.example/alice', headers=endpoint_1)
    requests_mock.get('https://same.example/bob', headers=endpoint_2)
    with pytest.raises(ValueError):
        indieauth.verify_id('https://same.example/alice', 'https://same.example/bob')

    # scheme upgrade is allowed as long as the endpoint stays the same
    requests_mock.get('http://upgrade.example', headers=endpoint_2)
    requests_mock.get('https://upgrade.example', headers=endpoint_2)
    assert indieauth.verify_id('http://upgrade.example', 'https://upgrade.example')


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
        data = {'state': parse_args(response.url)['state'], 'code': 'bogus'}
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

    # callback returns invalid identity URL
    requests_mock.post('http://endpoint/', text=json.dumps({'me': 'http://whitehouse.gov'}))
    requests_mock.get('http://whitehouse.gov', text='hello there')
    check_failure('Domain mismatch')


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
    <p class="e-note">I'm <em>Larry</em>. And you're not. <span class="p-pronouns">he/him</span></p>
    <a class="u-email" href="mailto:larry%40example.foo">larry at example dot foo</a>
    <img class="u-photo" src="plop.jpg">
    </div>"""

    profile_blob = {
        'avatar': "http://profile.example/plop.jpg",
        'bio': "I'm Larry. And you're not. he/him",
        'email': "larry@example.foo",
        'name': "larry",
        'pronouns': "he/him",
        'homepage': "https://example.foo/~user/",
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
