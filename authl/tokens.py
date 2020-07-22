"""
Token storage
=============

The provided implementations are intended merely as a starting point that works
for the most common cases with minimal external dependencies. In general, if
you're only running a service on a single endpoint, use
:py:class:`DictStore`, and if you want to be able to load-balance,
use :py:class:`Serializer`. However, it is quite reasonable to
provide your own implementation of :py:class:`TokenStore` which is
backed by a shared data store such as Redis or a database.

"""

import typing
from abc import ABC, abstractmethod

import expiringdict
import itsdangerous


class TokenStore(ABC):
    """

    Storage for tokens; given some data to store, returns an opaque
    identifier that can be used to reconstitute said token.

    """
    @abstractmethod
    def put(self, value: typing.Any) -> str:
        """ Generates a token with the specified stored values. """

    @abstractmethod
    def get(self, key: str, to_type=tuple) -> typing.Any:
        """
        Retrieves the token's value; raises `KeyError` if the token does not
        exist or is invalid.
        """

    @abstractmethod
    def remove(self, key: str):
        """ Removes the key from the backing store, if appropriate. Is a no-op
        if the key doesn't exist (or if there's no backing store). """

    def pop(self, key: str, to_type=tuple) -> typing.Any:
        """ Retrieves the token's values, and deletes the token from the backing
        store. Even if the value retrieval fails, it will be removed. """
        try:
            stored = self.get(key, to_type)
            return stored
        finally:
            self.remove(key)


class DictStore(TokenStore):
    """
    A token store that stores the token values in a dict-like container.

    This is suitable for the general case of having a single persistent service
    running on a single endpoint.

    The default storage is an `expiringdict`_ with a size limit of 1024 and a
    maximum lifetime of 1 hour. This can be tuned to your needs. In particular,
    the lifetime never needs to be any higher than your longest allowed
    transaction lifetime, and the size limit generally needs to be no more than
    the number of concurrent logins at any given time.

    .. _expiringdict: https://pypi.org/project/expiringdict/
    """

    def __init__(self, store: dict = None):
        """ Initialize the store """
        self._store: dict = expiringdict.ExpiringDict(
            max_len=1024,
            max_age_seconds=3600) if store is None else store

    def put(self, value):
        import uuid
        key = str(uuid.uuid4())
        self._store[key] = value
        return key

    def get(self, key, to_type=tuple):
        return to_type(self._store[key])

    def remove(self, key):
        try:
            del self._store[key]
        except KeyError:
            pass

    def pop(self, key, to_type=tuple):
        return to_type(self._store.pop(key))


class Serializer(TokenStore):
    """
    A token store that stores the token values within the token name, using
    a tamper-resistant signed serializer. Use this to avoid having a backing
    store entirely, although the tokens can get quite large.

    This is suitable for situations where you are load-balancing across multiple
    nodes, or need tokens to persist across frequent service restarts, and don't
    want to be dependent on a database. Note that all running instances will
    need to share the same secret_key.

    Also note that tokens stored in this way cannot be revoked individually.
    """

    def __init__(self, secret_key):
        """ Initializes the token store

        :param str secret_key: The signing key for the serializer
        """

        self._serializer = itsdangerous.URLSafeSerializer(secret_key)

    def put(self, value):
        return self._serializer.dumps(value)

    def get(self, key, to_type=tuple):
        try:
            return to_type(self._serializer.loads(key))
        except itsdangerous.BadData:
            raise KeyError("Invalid token")

    def remove(self, key):
        pass
