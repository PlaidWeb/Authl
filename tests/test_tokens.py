""" Tests of the TokenStore implementations """
# pylint:disable=missing-docstring


import pytest

from authl import disposition, tokens


def test_dictstore():
    store = tokens.DictStore({})

    # different values should have different keys
    token = store.put((1, 2, 3))
    token2 = store.put((1, 2, 3))
    assert token != token2
    assert isinstance(token, str)
    assert isinstance(token2, str)

    # getting repeatedly should succeed
    assert store.get(token) == (1, 2, 3)
    assert store.get(token) == (1, 2, 3)
    assert store.get(token) == (1, 2, 3)

    # popping should remove it
    assert store.pop(token) == (1, 2, 3)
    with pytest.raises(disposition.Error):
        store.get(token)
    with pytest.raises(disposition.Error):
        store.pop(token)

    # removal should also remove it
    store.remove(token2)
    with pytest.raises(disposition.Error):
        store.get(token2)
    with pytest.raises(disposition.Error):
        store.pop(token2)

    # getting nonexistent should fail
    with pytest.raises(disposition.Error):
        store.get('bogus')

    # removal should always work even if the token doesn't exist
    store.remove(token)
    store.remove(token2)
    store.remove('bogus')


def test_serializer():
    store = tokens.Serializer(__name__)

    # different values should get the same key
    token = store.put((1, 2, 3))
    token2 = store.put((1, 2, 3))
    assert token == token2
    assert isinstance(token, str)
    assert isinstance(token2, str)

    # getting repeatedly should succeed
    assert store.get(token) == (1, 2, 3)
    assert store.get(token) == (1, 2, 3)
    assert store.get(token) == (1, 2, 3)

    # popping won't remove it
    assert store.pop(token) == (1, 2, 3)
    assert store.get(token) == (1, 2, 3)

    # removal also won't remove it
    store.remove(token2)
    store.remove(token2)
    store.remove(token2)
    assert store.get(token2) == (1, 2, 3)

    # getting nonexistent should fail
    with pytest.raises(disposition.Error):
        store.get('bogus')

    # removal should always work even if the token doesn't exist
    store.remove(token)
    store.remove(token2)
    store.remove('bogus')
