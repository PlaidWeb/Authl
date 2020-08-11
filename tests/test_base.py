""" tests of the base handler """
# pylint:disable=missing-docstring

from . import TestHandler


def test_version():
    from authl import __version__
    assert __version__.__version__


def test_base_handler():
    handler = TestHandler()
    assert handler.handles_url('foo') is None
    assert handler.handles_page('foo', {}, {}, {}) is False
