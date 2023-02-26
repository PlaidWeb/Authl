""" main instance tests """

import pytest

import authl
from authl import Authl, tokens

from . import TestHandler


class UrlHandler(TestHandler):
    """ a handler that just handles a specific URL """

    def __init__(self, url, cid):
        self.url = url
        self.cid = cid

    @property
    def cb_id(self):
        return self.cid

    def handles_url(self, url):
        return url if url == self.url else None


class LinkHandler(TestHandler):
    """ a handler that just handles a page with a particular link rel """

    def __init__(self, rel, cid):
        self.rel = rel
        self.cid = cid

    @property
    def cb_id(self):
        return self.cid

    def handles_page(self, url, headers, content, links):
        return self.rel in links or content.find('link', rel=self.rel)


def test_register_handler():
    """ Test that both registration paths result in the same, correct result """
    handler = TestHandler()

    instance_1 = Authl([handler])
    assert list(instance_1.handlers) == [handler]

    instance_2 = Authl()
    instance_2.add_handler(handler)

    assert list(instance_1.handlers) == list(instance_2.handlers)

    with pytest.raises(ValueError):
        instance_2.add_handler(handler)


def test_get_handler_for_url(requests_mock):
    """ Test that URL rules map correctly """
    handler_1 = UrlHandler('test://foo', 'a')
    handler_2 = UrlHandler('test://bar', 'b')
    handler_3 = LinkHandler('moo', 'c')
    instance = Authl([handler_1, handler_2, handler_3])

    requests_mock.get('http://moo/link', text='<link rel="moo" href="yes">')
    requests_mock.get('http://moo/header', headers={'Link': '<gabba>; rel="moo"'})
    requests_mock.get('http://moo/redir', status_code=301,
                      headers={'Location': 'http://moo/header'})
    requests_mock.get('http://foo.bar', text="nothing here")

    assert instance.get_handler_for_url('test://foo') == (handler_1, 'a', 'test://foo')
    assert instance.get_handler_for_url('test://bar') == (handler_2, 'b', 'test://bar')
    assert instance.get_handler_for_url('test://baz') == (None, '', '')

    assert instance.get_handler_for_url(' test://foo ') == (handler_1, 'a', 'test://foo')

    assert instance.get_handler_for_url('http://moo/link') == \
        (handler_3, 'c', 'http://moo/link')
    assert instance.get_handler_for_url('http://moo/header') == \
        (handler_3, 'c', 'http://moo/header')
    assert instance.get_handler_for_url('http://moo/redir') == \
        (handler_3, 'c', 'http://moo/header')

    assert instance.get_handler_for_url('http://foo.bar') == (None, '', '')

    assert instance.get_handler_for_url('') == (None, '', '')


def test_from_config(mocker):
    """ Ensure the main from_config function calls the appropriate proxied ones """
    test_config = {
        'EMAIL_FROM': 'hello',
        'FEDIVERSE_NAME': 'hello',
        'INDIEAUTH_CLIENT_ID': 'hello',
        'TWITTER_CLIENT_KEY': 'hello',
        'TEST_ENABLED': True
    }

    mocks = {}

    handler_modules = (('email_addr', tokens.DictStore),
                       ('fediverse', tokens.DictStore),
                       ('indieauth', tokens.DictStore),
                       ('twitter', dict))

    for name, _ in handler_modules:
        mocks[name] = mocker.patch(f'authl.handlers.{name}.from_config')

    mock_test_handler = mocker.patch('authl.handlers.test_handler.TestHandler')

    authl.from_config(test_config)

    for name, storage_type in handler_modules:
        mocks[name].assert_called_once()
        config, storage = mocks[name].call_args[0]
        assert config == test_config
        assert isinstance(storage, storage_type)

    mock_test_handler.assert_called_once()
    assert mock_test_handler.call_args == (())


def test_redir_url(requests_mock):
    """ Ensure that redirected profile pages match URL rules for the redirect """
    requests_mock.get('http://foo', status_code=301, headers={'Location': 'http://bar'})
    requests_mock.get('http://bar', text='blah')
    handler = UrlHandler('http://bar', 'foo')
    instance = Authl([handler])

    assert instance.get_handler_for_url('http://foo') == \
        (handler, 'foo', 'http://bar')


def test_webfinger_profiles(mocker):
    """ test handles_url on a webfinger profile """
    handler_1 = UrlHandler('test://foo', 'a')
    handler_2 = UrlHandler('test://bar', 'b')
    instance = Authl([handler_1, handler_2])

    wgp = mocker.patch('authl.webfinger.get_profiles')
    wgp.side_effect = lambda url: {'test://cat',
                                   'test://bar'} if url == 'fake webfinger address' else {}

    assert instance.get_handler_for_url('fake webfinger address') == (handler_2, 'b', 'test://bar')


def test_scheme_fallback(requests_mock):
    """ Ensure that unknown and missing schemes fall back correctly """
    requests_mock.get('https://foo/bar', text='blah')
    requests_mock.get('http://foo/bar', text='blah')

    handler_https = UrlHandler('https://foo/bar', 'secure')
    handler_http = UrlHandler('http://foo/bar', 'insecure')
    instance = Authl([handler_https, handler_http])

    assert instance.get_handler_for_url(
        'https://foo/bar') == (handler_https, 'secure', 'https://foo/bar')
    assert instance.get_handler_for_url(
        'http://foo/bar') == (handler_http, 'insecure', 'http://foo/bar')
    assert instance.get_handler_for_url('foo/bar') == (handler_https, 'secure', 'https://foo/bar')
    assert instance.get_handler_for_url('example://foo') == (None, '', '')


def test_relme_auth(requests_mock):
    """ test RelMeAuth profile support """
    handler_1 = UrlHandler('test://foo', 'a')
    handler_2 = UrlHandler('https://social.example/bob', 'b')
    instance = Authl([handler_1, handler_2])

    requests_mock.get('https://foo-link.example/', text='<link rel="me" href="test://foo">')
    requests_mock.get('https://foo-a.example/', text='<a rel="me" href="test://foo">')
    requests_mock.get('https://header.example/', headers={'Link': '<test://foo>; rel="me"'})

    requests_mock.get('https://social.example/relative-link', text='<link rel="me" href="bob">')
    requests_mock.get('https://social.example/relative-a', text='<a rel="me" href="bob">')
    requests_mock.get('https://multiple.example/', text='''
        <link rel="me" href="test://bar">
        <link rel="me" href="test://baz">
        <a href="https://social.example/bob" rel="me">
        ''')

    for url in ('https://foo-link.example/',
                'https://foo-a.example',
                'https://header.example'):
        assert instance.get_handler_for_url(url) == (handler_1, 'a', 'test://foo')

    for url in ('https://social.example/relative-link',
                'https://social.example/relative-a',
                'https://multiple.example/'):
        assert instance.get_handler_for_url(url) == (handler_2, 'b', 'https://social.example/bob')
