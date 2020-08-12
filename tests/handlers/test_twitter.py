""" Tests for the Twitter handler """
# pylint:disable=missing-docstring

import pytest

from authl import disposition
from authl.handlers import twitter

from . import parse_args


def test_from_config():
    with pytest.raises(KeyError):
        twitter.from_config({'TWITTER_CLIENT_KEY': 'foo'}, {})

    handler = twitter.from_config({'TWITTER_CLIENT_KEY': 'foo',
                                   'TWITTER_CLIENT_SECRET': 'bar'}, {})
    assert isinstance(handler, twitter.Twitter)


def test_basics():
    handler = twitter.Twitter('foo', 'bar')
    assert handler.service_name == 'Twitter'
    assert handler.url_schemes
    assert 'twitter.com' in handler.description
    assert handler.cb_id == 't'
    assert handler.logo_html[0][1] == 'Twitter'
    assert handler.generic_url

    assert handler.handles_url('twitter.com') == 'https://twitter.com/'
    assert handler.handles_url('twitter.com/fluffy') == 'https://twitter.com/fluffy'
    assert handler.handles_url('twitter.com/@fluffy') == 'https://twitter.com/fluffy'
    assert handler.handles_url(
        'https://twitter.com/fluffy?utm_source=foo') == 'https://twitter.com/fluffy'
    assert not handler.handles_url('https://foo.bar/baz')


def test_misconfigured(mocker):
    storage = {}
    handler = twitter.Twitter('foo', 'bar', 60, storage)

    mocker.patch("authl.handlers.twitter.OAuth1")
    session_mock = mocker.patch("authl.handlers.twitter.OAuth1Session")

    session_mock = mocker.patch("authl.handlers.twitter.OAuth1Session")
    session_mock().fetch_request_token.side_effect = ValueError("bad config")

    result = handler.initiate_auth('https://twitter.com/fluffy', 'http://cb', 'failure')
    assert isinstance(result, disposition.Error), str(result)
    assert 'bad config' in result.message
    assert result.redir == 'failure'


def test_auth_success(mocker, requests_mock):
    storage = {}
    handler = twitter.Twitter('foo', 'bar', 60, storage)

    # Test gets successful initiation
    mocker.patch("authl.handlers.twitter.OAuth1")
    session_mock = mocker.patch("authl.handlers.twitter.OAuth1Session")

    session_mock().fetch_request_token.return_value = {
        'oauth_token': 'my_token',
        'oauth_token_secret': 'my_secret'
    }

    result = handler.initiate_auth('https://twitter.com/fluffy', 'http://cb', 'redir')

    assert isinstance(result, disposition.Redirect), str(result)
    assert result.url.startswith('https://api.twitter.com')

    args = parse_args(result.url)
    print(result.url)
    assert args['screen_name'] == 'fluffy'
    assert args['oauth_token'] == 'my_token'
    assert 'my_token' in storage

    result = handler.check_callback('foo', {'oauth_token': 'blop'}, {})
    assert isinstance(result, disposition.Error)
    assert 'Invalid transaction' in result.message

    requests_mock.get('https://api.twitter.com/1.1/account/verify_credentials.json?skip_status=1',
                      json={'screen_name': 'foo',
                            'id_str': '12345'})
    cleanup = requests_mock.post(
        'https://api.twitter.com/1.1/oauth/invalidate_token.json', text="okay")

    args['oauth_verifier'] = 'verifier'

    result = handler.check_callback('foo', args, {})
    assert isinstance(result, disposition.Verified), str(result)
    assert result.redir == 'redir'
    assert result.identity == 'https://twitter.com/foo#12345'

    # guard against replay attacks
    result = handler.check_callback('foo', args, {})
    assert isinstance(result, disposition.Error), str(result)

    assert cleanup.called


def test_auth_failures(mocker, requests_mock):
    storage = {}
    handler = twitter.Twitter('foo', 'bar', 60, storage)

    mocker.patch("authl.handlers.twitter.OAuth1")
    session_mock = mocker.patch("authl.handlers.twitter.OAuth1Session")

    # Test attempt at authenticating against non-twitter URL
    result = handler.initiate_auth('https://foo.example', 'http://cb', 'redir')
    assert isinstance(result, disposition.Error), "tried to handle non-twitter URL"

    # test timeouts
    session_mock().fetch_request_token.return_value = {
        'oauth_token': 'my_token',
        'oauth_token_secret': 'my_secret'
    }

    mock_time = mocker.patch('time.time')
    mock_time.return_value = 12345
    result = handler.initiate_auth('https://twitter.com/', 'http://cb', 'timeout')
    assert isinstance(result, disposition.Redirect), str(result)
    args = parse_args(result.url)
    args['oauth_verifier'] = 'verifier'

    mock_time.return_value = 12345678
    result = handler.check_callback('foo', args, {})
    assert isinstance(result, disposition.Error), str(result)
    assert 'timed out' in result.message

    # test internal failure
    result = handler.initiate_auth('https://twitter.com/', 'http://cb', 'timeout')
    assert isinstance(result, disposition.Redirect), str(result)
    args = parse_args(result.url)
    args['oauth_verifier'] = 'verifier'

    requests_mock.get('https://api.twitter.com/1.1/account/verify_credentials.json?skip_status=1',
                      json=['not a valid response'])
    cleanup = requests_mock.post(
        'https://api.twitter.com/1.1/oauth/invalidate_token.json', text="okay")

    result = handler.check_callback('foo', args, {})
    assert isinstance(result, disposition.Error), str(result)
    assert 'object has no attribute' in result.message, str(result)
    assert cleanup.called


def test_auth_denied(mocker):
    storage = {}
    handler = twitter.Twitter('foo', 'bar', 60, storage)

    # Test gets successful initiation
    mocker.patch("authl.handlers.twitter.OAuth1")
    session_mock = mocker.patch("authl.handlers.twitter.OAuth1Session")

    session_mock().fetch_request_token.return_value = {
        'oauth_token': 'my_token',
        'oauth_token_secret': 'my_secret'
    }

    result = handler.initiate_auth('https://twitter.com/fluffy', 'http://cb', 'redir')

    assert isinstance(result, disposition.Redirect), str(result)
    assert result.url.startswith('https://api.twitter.com')

    args = parse_args(result.url)
    print(result.url)
    assert args['screen_name'] == 'fluffy'
    assert args['oauth_token'] == 'my_token'
    assert 'my_token' in storage

    args['denied'] = args.pop('oauth_token')
    result = handler.check_callback('foo', args, {})
    assert isinstance(result, disposition.Error)
    assert 'authorization declined' in result.message


def test_profile(requests_mock):
    user_info = {
        'profile_image_url_https': 'http://example.com/foo_normal.jpg',
        'description': 'this is a biography. see more at https://is.gd/notareallink',
        'entities': {
            'description': {
                'urls': [
                    {'url': 'https://is.gd/notareallink', 'expanded_url': 'https://beesbuzz.biz/'}
                ]
            }
        }
    }

    requests_mock.head('http://example.com/foo_400x400.jpg', status_code=200)

    handler = twitter.Twitter('foo', 'bar')
    profile = handler.build_profile(user_info)
    assert profile == {
        'avatar': 'http://example.com/foo_400x400.jpg',
        'bio': 'this is a biography. see more at https://beesbuzz.biz/'
    }
