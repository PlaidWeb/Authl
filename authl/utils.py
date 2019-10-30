""" Utility functions """

import html
import logging
import re

import itsdangerous
import requests

from . import disposition

LOGGER = logging.getLogger(__name__)


def read_file(filename):
    """ Given a filename, read the entire thing into a string """
    with open(filename, encoding='utf-8') as file:
        return file.read()


def get_webfinger_profile(user, domain):
    """ Get the webfinger profile page URL from a webfinger query """
    resource = 'https://{}/.well-known/webfinger?resource={}'.format(
        domain,
        html.escape('acct:{}@{}'.format(user, domain)))
    request = requests.get(resource)

    if not 200 <= request.status_code < 300:
        LOGGER.info("Webfinger query %s returned status code %d", resource, request.status_code)
        LOGGER.debug("%s", request.text)
        return None

    try:
        profile = request.json()
    except ValueError:
        LOGGER.info("Profile decode of %s failed", resource)
        return None

    try:
        for link in profile['links']:
            if link['rel'] == 'http://webfinger.net/rel/profile-page':
                return link['href']
    except Exception as err:  # pylint:disable=broad-except
        LOGGER.info("Failed to decode %s profile: %s", resource, err)
        return None

    LOGGER.info("Could not find profile page for @%s@%s", user, domain)
    return None


def request_url(url):
    """ Requests a URL, attempting to canonicize it as it goes """
    # pylint:disable=broad-except

    # webfinger addresses should be treated as the profile URL instead
    webfinger = re.match(r'@([^@])+@(.*)$', url)
    if webfinger:
        url = get_webfinger_profile(webfinger.group(1), webfinger.group(2))
    if not url:
        return None

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
        raise disposition.Error("Invalid login", None)

    return cdata, redir
