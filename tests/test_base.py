""" tests of the base handler """
# pylint:disable=missing-docstring

from . import TestHandler


def test_base_handler():
    handler = TestHandler()
    assert handler.handles_url('foo') is None
    assert handler.handles_page('foo', {}, {}, {}) is False
