""" Tests for the various utility functions """
# pylint:disable=missing-docstring

import requests_mock

from authl import utils


def test_request_url():
    with requests_mock.Mocker() as mock:
        mock.get('http://example.com/', text='insecure')

        assert utils.request_url('example.com').text == 'insecure'

        mock.get('https://example.com/', text='secure')

        assert utils.request_url('example.com').text == 'secure'
        assert utils.request_url('https://example.com').text == 'secure'
        assert utils.request_url('http://example.com').text == 'insecure'

        assert utils.request_url('http://nonexistent') is None
        assert utils.request_url('invalid://protocol') is None

        mock.get('https://has.links/', headers={'Link': '<https://foo>; rel="bar"'})
        assert utils.request_url('has.links').links['bar']['url'] == 'https://foo'


def test_resolve_value():
    def moo():
        return 5
    assert utils.resolve_value(moo) == 5
    assert utils.resolve_value(10) == 10
