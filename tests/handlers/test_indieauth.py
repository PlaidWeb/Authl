""" Tests of the IndieAuth handler """
# pylint:disable=missing-docstring


import json
import logging
import urllib.parse

import itsdangerous
import pytest
import requests
import requests_mock
from bs4 import BeautifulSoup

from authl import disposition
from authl.handlers import indieauth

LOGGER = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def purge_endpoint_cache():
    # pylint:disable=protected-access
    indieauth._ENDPOINT_CACHE.clear()


def test_find_endpoint_by_url():
    from authl.handlers.indieauth import find_endpoint
    with requests_mock.Mocker() as mock:
        mock.get('http://link.absolute/', text='Nothing to see',
                 headers={'Link': '<https://endpoint/>; rel="authorization_endpoint"'})

        assert find_endpoint('http://link.absolute/') == 'https://endpoint/'

        mock.get('http://link.relative/', text='Nothing to see',
                 headers={'Link': '<invalid>; rel="authorization_endpoint"'})
        assert find_endpoint('http://link.relative/') == 'invalid'

        mock.get('http://content.absolute/',
                 text='<link rel="authorization_endpoint" href="https://endpoint/">')
        assert find_endpoint('http://content.absolute/') == 'https://endpoint/'

        mock.get('http://content.relative/',
                 text='<link rel="authorization_endpoint" href="endpoint" >')
        assert find_endpoint('http://content.relative/') == 'http://content.relative/endpoint'

        mock.get('http://both/',
                 text='<link rel="authorization_endpoint" href="http://content/endpoint">',
                 headers={'Link': '<https://header/endpoint/>; rel="authorization_endpoint"'}
                 )
        assert find_endpoint('http://both/') == 'https://header/endpoint/'

        mock.get('http://nothing/', text='nothing')
        assert find_endpoint('http://nothing/') is None

        # test the caching
        mock.reset()
        assert find_endpoint('http://link.absolute/') == 'https://endpoint/'
        assert find_endpoint('http://link.relative/') == 'invalid'
        assert find_endpoint('http://content.absolute/') == 'https://endpoint/'
        assert find_endpoint('http://content.relative/') == 'http://content.relative/endpoint'
        assert not mock.called

        # but a failed lookup shouldn't be cached
        assert find_endpoint('http://nothing/') is None
        assert mock.called


def test_find_endpoint_by_content():
    links = {'authorization_endpoint': {'url': 'http://link_endpoint'}}
    rel_content = BeautifulSoup('<link rel="authorization_endpoint" href="foo">',
                                'html.parser')
    abs_content = BeautifulSoup('<link rel="authorization_endpoint" href="http://foo/">',
                                'html.parser')

    with requests_mock.Mocker() as mock:
        assert indieauth.find_endpoint('http://example', links=links) == 'http://link_endpoint'
        assert indieauth.find_endpoint('http://example',
                                       content=rel_content) == 'http://example/foo'
        assert indieauth.find_endpoint('http://example', content=abs_content) == 'http://foo/'

        # link header overrules page content
        assert indieauth.find_endpoint('http://example',
                                       links=links,
                                       content=rel_content) == 'http://link_endpoint'

        assert not mock.called


def test_verify_id():
    # allowed things
    for src, dest in (
            # exact match
            ('http://example.com', 'http://example.com'),
            ('http://example.com/', 'http://example.com/'),

            # change in trailing slash
            ('http://example.com/', 'http://example.com'),
            ('http://example.com', 'http://example.com/'),

            # scheme change (expressly allowed in
            # https://indieauth.spec.indieweb.org/#authorization-code-verification)
            ('http://example.com', 'https://example.com'),

            # Path additions
            ('http://example.com', 'http://example.com/user'),
            ('http://example.com/user', 'http://example.com/user'),
            ('http://example.com/user', 'http://example.com/user/'),
            ('http://example.com/user', 'http://example.com/user/./'),
            ('http://example.com/user', 'http://example.com/user/../user'),
    ):
        assert indieauth.verify_id(src, dest)

    # disallowed things
    for src, dest in (
            # different domain
            ('https://foo.bar/', 'https://baz/'),
            ('https://foo.bar/', 'https://www.foo.bar/'),

            # provisional/proposed change to requiring paths to only become more specific
            # https://github.com/indieweb/indieauth/issues/35
            ('https://example.com/alice', 'https://example.com/bob'),
            ('https://example.com/alice/../bob', 'https://example.com/bob'),
            ('https://example.com/user/', 'https://example.com/'),
            ('https://example.com/user/', 'https://example.com/user/../../../../../'),
    ):
        assert not indieauth.verify_id(src, dest)


def parse_args(url):
    url = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(url.query)
    return {key: val[0] for key, val in params.items()}


def test_handler_details():
    tokens = itsdangerous.URLSafeTimedSerializer('test_handler')
    handler = indieauth.IndieAuth('http://client/', tokens)

    with requests_mock.Mocker() as mock:
        assert handler.service_name
        assert handler.url_schemes
        assert handler.description
        assert handler.cb_id
        assert handler.logo_html

        # profile page at http://example.user/
        mock.get('http://example.user/',
                 text="heñlo",
                 headers={'Link': '<http://endpoint/>; rel="authorization_endpoint"'})

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
        assert disp.url.startswith('http://endpoint/')

        # fake the user dialog on the IndieAuth endpoint
        user_get = parse_args(disp.url)
        assert user_get['redirect_uri'].startswith('http://client/cb')
        assert 'client_id' in user_get
        assert 'state' in user_get
        assert user_get['response_type'] == 'id'
        assert 'me' in user_get

        # fake the verification response
        def verify_callback(request, _):
            args = urllib.parse.parse_qs(request.text)
            assert args['code'] == ['asdf']
            assert args['client_id'] == ['http://client/']
            assert 'redirect_uri' in args
            return json.dumps({
                'me': 'http://example.user/bob'
            })
        mock.post('http://endpoint/', text=verify_callback)

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
        assert response.identity == 'http://example.user/bob'
        assert response.redir == '/dest'


def test_handler():
    tokens = itsdangerous.URLSafeTimedSerializer('test_handler')
    handler = indieauth.IndieAuth('http://client/', tokens)

    with requests_mock.Mocker() as mock:
        # Attempt to auth against page with no endpoint
        mock.get('http://no-endpoint/', text='hello')
        response = handler.initiate_auth('http://no-endpoint/', 'http://cb/', 'bogus')
        assert isinstance(response, disposition.Error)
        assert 'endpoint' in response.message

        # Attempt to inject a transaction-less callback response
        response = handler.check_callback('http://no-transaction', {}, {})
        assert isinstance(response, disposition.Error)
        assert 'No transaction' in response.message

        # Attempt to inject a forged callback response
        response = handler.check_callback('http://bogus-transaction', {'state': 'bogus'}, {})
        assert isinstance(response, disposition.Error)
        assert 'Invalid token' in response.message

        # Get a valid state token
        mock.get('http://example.user/',
                 text='hello',
                 headers={'Link': '<http://endpoint/>; rel="authorization_endpoint"'})

        response = handler.initiate_auth('http://example.user', 'http://client/cb', '/dest')
        assert isinstance(response, disposition.Redirect)
        data = {'state': parse_args(response.url)['state']}

        # no code assigned
        assert "Missing 'code'" in handler.check_callback('http://client/cb', data, {}).message

        def check_failure(message):
            response = handler.initiate_auth('http://example.user', 'http://client/cb', '/dest')
            assert isinstance(response, disposition.Redirect)
            data = {'state': parse_args(response.url)['state'], 'code': 'bogus'}
            response = handler.check_callback('http://client/cb', data, {})
            assert isinstance(response, disposition.Error)
            assert message in response.message

        # callback returns error
        mock.post('http://endpoint/', status_code=400)
        check_failure('returned 400')

        # callback returns broken JSON
        mock.post('http://endpoint/', text='invalid json')
        check_failure('invalid response JSON')

        # callback returns invalid identity URL
        mock.post('http://endpoint/', text=json.dumps({'me': 'http://whitehouse.gov'}))
        check_failure('does not match')


def test_from_config():
    # pylint:disable=protected-access
    handler = indieauth.from_config({'INDIEAUTH_CLIENT_ID': 'poiu',
                                     'INDIEAUTH_PENDING_TTL': 12345}, "plop")
    assert isinstance(handler, indieauth.IndieAuth)
    assert handler._client_id == 'poiu'
    assert handler._timeout == 12345
    assert handler._token_store == "plop"
