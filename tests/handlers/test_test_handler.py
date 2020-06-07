""" Tests for the loopback handler """
# pylint:disable=missing-function-docstring

from authl import disposition
from authl.handlers.test_handler import TestHandler


def test_handling():
    handler = TestHandler()
    assert handler.handles_url('test:foo')
    assert handler.handles_url('test:error')
    assert not handler.handles_url('https://example.com')


def test_success():
    handler = TestHandler()

    positive = handler.initiate_auth('test:admin', 'https://example.com/bar', 'target')
    assert isinstance(positive, disposition.Verified)
    assert positive.identity == 'test:admin'
    assert positive.redir == 'target'
    assert positive.profile == {}


def test_failure():
    handler = TestHandler()

    negative = handler.initiate_auth('test:error', 'https://example.com/bar', 'target')
    assert isinstance(negative, disposition.Error)
    assert "Error identity" in negative.message
    assert negative.redir == 'target'


def test_callback():
    handler = TestHandler()

    assert isinstance(handler.check_callback('foo', {}, {}), disposition.Error)


def test_misc():
    handler = TestHandler()
    assert handler.cb_id
    assert handler.service_name == 'Loopback'
    assert handler.url_schemes
    assert handler.description
