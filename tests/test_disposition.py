""" Disposition tests, such as they are """
# pylint:disable=missing-docstring

from authl import disposition


def test_dispositions():
    assert 'foo' in str(disposition.Redirect('foo'))
    assert 'foo' in str(disposition.Verified('foo', None))
    assert 'foo' in str(disposition.Notify('foo'))
    assert 'foo' in str(disposition.Error('foo', None))
    assert 'foo' in str(disposition.NeedsPost('', 'foo', {}))
