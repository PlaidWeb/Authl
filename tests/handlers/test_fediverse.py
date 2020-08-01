""" Tests of the Fediverse handler """
# pylint:disable=missing-docstring

import json
import logging
from unittest.mock import patch

import mastodon
import requests_mock

from authl import disposition, tokens
from authl.handlers import fediverse

from . import parse_args

LOGGER = logging.getLogger(__name__)


def test_basics():
    handler = fediverse.from_config({
        'FEDIVERSE_NAME': 'test',
        'MASTODON_HOMEPAGE': 'http://foo.bar/',
    }, tokens.DictStore())
    assert handler.service_name
    assert handler.url_schemes
    assert handler.description
    assert handler.cb_id
    assert handler.logo_html


def test_handles_url():
    handler = fediverse.Fediverse('test', tokens.DictStore(), homepage='http://foo.example/')

    with requests_mock.Mocker() as mock:
        mock.get('https://mastodon.example/api/v1/instance',
                 text=json.dumps({
                     'uri': 'foo',
                     'version': '2.5.1',
                     'urls': 'foo.bar'
                 }))

        mock.get('https://not-mastodon.example/api/v1/instance',
                 text=json.dumps({
                     'moo': 'cow'
                 }))

        mock.get('https://also-not.example/api/v1/instance', status_code=404)

        assert handler.handles_url('https://mastodon.example/@fluffy')
        assert handler.handles_url('https://mastodon.example/')
        assert handler.handles_url('mastodon.example')
        assert not handler.handles_url('https://not-mastodon.example/@fluffy')
        assert not handler.handles_url('https://not-mastodon.example/')
        assert not handler.handles_url('https://blah.example/')
        assert not handler.handles_url('https://also-not.example/')


def test_auth_success():
    store = tokens.DictStore()
    handler = fediverse.Fediverse('test', store, homepage='http://foo.example/')
    with requests_mock.Mocker() as mock_requests, patch('mastodon.Mastodon') as mock_mastodon:
        mock_mastodon.create_app.return_value = ('the id', 'the secret')
        mock_mastodon().auth_request_url.return_value = 'https://cb?code=12345'
        mock_mastodon().log_in.return_value = 'some_auth_token'
        mock_mastodon().me.return_value = {
            'url': 'https://mastodon.example/@moo',
            'display_name': 'moo friend',
            'avatar_static': 'https://placekitten.com/1280/1024',
            'source': {
                'note': 'a cow',
                'fields': [
                    {'name': 'homepage', 'value': 'https://moo.example'},
                    {'name': 'my pronouns', 'value': 'moo/moo'}
                ]
            }
        }

        mock_requests.get('https://mastodon.example/api/v1/instance',
                          text=json.dumps({
                              'uri': 'foo',
                              'version': '2.5.1',
                              'urls': 'foo.bar'
                          }))

        mock_requests.post('https://mastodon.example/oauth/revoke', text='ok')

        result = handler.initiate_auth('mastodon.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        mock_mastodon().auth_request_url.assert_called_with(
            redirect_uris='https://cb', scopes=['read:accounts'])

        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Verified)
        assert result.identity == 'https://mastodon.example/@moo'
        assert result.redir == 'qwerpoiu'
        assert result.profile == {
            'name': 'moo friend',
            'bio': 'a cow',
            'avatar': 'https://placekitten.com/1280/1024',
            'homepage': 'https://moo.example',
            'pronouns': 'moo/moo'
        }


def test_auth_failures():
    # pylint:disable=too-many-statements
    store = tokens.DictStore({})
    handler = fediverse.Fediverse('test', store, homepage='http://foo.example/')
    with requests_mock.Mocker() as mock_requests, patch('mastodon.Mastodon') as mock_mastodon:
        # nonexistent instance
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Error)
        assert 'Failed to register client' in result.message

        # not a mastodon instance
        mock_requests.get('https://fail.example/api/v1/instance', text="'lolwut'")
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Error)
        assert 'Failed to register client' in result.message

        # okay now it's an instance
        mock_requests.get('https://fail.example/api/v1/instance',
                          text=json.dumps({
                              'uri': 'foo',
                              'version': '2.5.1',
                              'urls': 'foo.bar'
                          }))
        mock_mastodon.create_app.return_value = ('the id', 'the secret')

        # missing auth code
        mock_mastodon().auth_request_url.return_value = 'https://cb?foo=bar'
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Error)
        assert "Missing 'code'" in result.message

        # Login was aborted
        mock_mastodon().auth_request_url.return_value = 'https://cb?code=12345&error=nope'
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Error)
        assert "Error signing into instance" in result.message

        mock_mastodon().auth_request_url.return_value = 'https://cb?code=yep'

        # login failed for some other reason
        mock_mastodon().log_in.side_effect = mastodon.MastodonRatelimitError("stop it")
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Error)
        assert "Error signing into instance" in result.message

        mock_mastodon().log_in.side_effect = None
        mock_mastodon().log_in.return_value = 'some auth code'

        # login expired
        with patch('time.time') as mock_time:
            mock_time.return_value = 100
            result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
            assert isinstance(result, disposition.Redirect)

            mock_time.return_value = 86400
            result = handler.check_callback(result.url, parse_args(result.url), {})
            assert isinstance(result, disposition.Error)
            assert 'Login timed out' in result.message

        # broken profile
        mock_mastodon().me.return_value = {}
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Error)
        assert 'Missing user profile' in result.message

        mock_mastodon().me.return_value = {
            'url': 'https://fail.example/@larry',
            'source': ['ha ha ha', 'i break you']
        }
        result = handler.initiate_auth('fail.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Error)
        assert 'Malformed user profile' in result.message


def test_attack_mitigations():
    store = tokens.DictStore()
    handler = fediverse.Fediverse('test', store, homepage='http://foo.example/')
    with requests_mock.Mocker() as mock_requests, patch('mastodon.Mastodon') as mock_mastodon:
        mock_mastodon.create_app.return_value = ('the id', 'the secret')
        mock_mastodon().auth_request_url.return_value = 'https://cb?code=12345'
        mock_mastodon().log_in.return_value = 'some_auth_token'

        mock_requests.get('https://mastodon.example/api/v1/instance',
                          text=json.dumps({
                              'uri': 'foo',
                              'version': '2.5.1',
                              'urls': 'foo.bar'
                          }))

        # domain hijack
        mock_mastodon().me.return_value = {
            'url': 'https://hijack.example/@moo',
        }
        result = handler.initiate_auth('mastodon.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        result = handler.check_callback(result.url, parse_args(result.url), {})
        assert isinstance(result, disposition.Error)
        assert 'Domains do not match' in result.message

        # attempted replay attack
        mock_mastodon().me.return_value = {
            'url': 'https://mastodon.example/@moo',
        }
        result = handler.initiate_auth('mastodon.example', 'https://cb', 'qwerpoiu')
        assert isinstance(result, disposition.Redirect)
        args = parse_args(result.url)
        result = handler.check_callback(result.url, args, {})
        assert isinstance(result, disposition.Verified)
        assert result.identity == 'https://mastodon.example/@moo'
        result = handler.check_callback('https://cb', args, {})
        assert isinstance(result, disposition.Error)
        assert 'Invalid transaction' in result.message
