""" Utility functions """

import collections
import html
import logging
import re
import typing

import itsdangerous
import requests

from . import disposition

LOGGER = logging.getLogger(__name__)


def read_file(filename):
    """ Given a filename, read the entire thing into a string """
    with open(filename, encoding='utf-8') as file:
        return file.read()


def get_webfinger_profiles(url: str) -> typing.Set[str]:
    """ Get the potential profile page URLs from a webfinger query """
    webfinger = re.match(r'@([^@])+@(.*)$', url)
    if not webfinger:
        return set()

    try:
        user, domain = webfinger.group(1, 2)

        resource = 'https://{}/.well-known/webfinger?resource={}'.format(
            domain,
            html.escape('acct:{}@{}'.format(user, domain)))
        request = requests.get(resource)

        if not 200 <= request.status_code < 300:
            LOGGER.info("Webfinger query %s returned status code %d",
                        resource, request.status_code)
            LOGGER.debug("%s", request.text)
            # Service doesn't support webfinger, so just pretend it's the most
            # common format for a profile page
            return {'https://{}/@{}'.format(domain, user)}

        profile = request.json()

        return {link['href'] for link in profile['links']
                if link['rel'] in ('http://webfinger.net/rel/profile-page', 'profile', 'self')}
    except Exception as err:  # pylint:disable=broad-except
        LOGGER.info("Failed to decode %s profile: %s", resource, err)
        return set()


def request_url(url):
    """ Requests a URL, attempting to canonicize it as it goes """
    # pylint:disable=broad-except

    try:
        return requests.get(url)
    except requests.exceptions.MissingSchema:
        LOGGER.info("Missing schema on URL %s", url)
    except (requests.exceptions.InvalidSchema, requests.exceptions.InvalidURL):
        LOGGER.info("Not a valid URL scheme: %s", url)
        return None
    except Exception as err:
        LOGGER.info("%s failed: %s", url, err)

    for prefix in ('https://', 'http://'):
        try:
            attempt = prefix + url
            LOGGER.debug("attempting %s", attempt)
            return requests.get(attempt)
        except Exception as err:
            LOGGER.info("%s failed: %s", attempt, err)

    return None


def resolve_value(val):
    """ if given a callable, call it; otherwise, return it """
    if callable(val):
        return val()
    return val


def unpack_token(token_store, token: str, timeout: int) -> tuple:
    """ Given a token_store, a token, and a timeout, try to unpack the data.
    The token ***must*** be packed in the form of (client_data,redir).

    On error, raises a disposition.Error which should be returned directly.
    It is up to the handler to catch and return this!
    """
    try:
        try:
            cdata, redir = token_store.loads(token, max_age=timeout)
        except itsdangerous.SignatureExpired:
            _, redir = token_store.loads(token)
            raise disposition.Error("Login has expired", redir)
    except itsdangerous.BadData:
        raise disposition.Error("Invalid token", None)

    return cdata, redir


class LRUDict(collections.OrderedDict):
    """ a Dict that has a size limit

    borrowed from
    https://docs.python.org/3/library/collections.html#ordereddict-examples-and-recipes
    """

    def __init__(self, *args, maxsize=128, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            self.popitem(False)
