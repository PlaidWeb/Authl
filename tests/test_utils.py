""" Tests for the various utility functions """
# pylint:disable=missing-docstring


import requests

from authl import utils


def test_request_url(requests_mock):
    requests_mock.get('http://example.com/', text='insecure')

    assert utils.request_url('example.com').text == 'insecure'

    requests_mock.get('https://example.com/', text='secure')

    assert utils.request_url('example.com').text == 'secure'
    assert utils.request_url('https://example.com').text == 'secure'
    assert utils.request_url('http://example.com').text == 'insecure'

    assert utils.request_url('http://nonexistent') is None
    assert utils.request_url('invalid://protocol') is None

    requests_mock.get('https://has.links/', headers={'Link': '<https://foo>; rel="bar"'})
    assert utils.request_url('has.links').links['bar']['url'] == 'https://foo'


def test_resolve_value():
    def moo():
        return 5
    assert utils.resolve_value(moo) == 5
    assert utils.resolve_value(10) == 10


def test_permanent_url(requests_mock):
    requests_mock.get('http://make-secure.example', status_code=301,
                      headers={'Location': 'https://make-secure.example'})
    requests_mock.get('https://make-secure.example', status_code=302,
                      headers={'Location': 'https://make-secure.example/final'})
    requests_mock.get('https://make-secure.example/final', text="you made it!")

    # this redirects permanent to https, which redirects temporary to /final
    req = requests.get('http://make-secure.example')
    assert utils.permanent_url(req) == 'https://make-secure.example'

    # direct request to /final should remain /final
    req = requests.get('https://make-secure.example/final')
    assert utils.permanent_url(req) == 'https://make-secure.example/final'

    # ensure 308 redirect works too
    requests_mock.get('http://perm-308.example', status_code=308,
                      headers={'Location': 'https://make-secure.example/308'})
    requests_mock.get('https://make-secure.example/308', status_code=401)

    req = requests.get('http://perm-308.example')
    assert utils.permanent_url(req) == 'https://make-secure.example/308'
