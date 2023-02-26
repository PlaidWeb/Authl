""" Utility functions """

import base64
import hashlib
import logging
import os.path
import typing
import urllib.parse
from typing import Optional

import requests

from . import __version__

LOGGER = logging.getLogger(__name__)

USER_AGENT = f'Authl v{__version__.__version__}; +https://plaidweb.site/'


def get_user_agent(client_id: Optional[str] = None):
    ''' Make a useful user-agent string for a request '''
    return f'{USER_AGENT} for {client_id}' if client_id else USER_AGENT


def read_file(filename):
    """ Given a filename, read the entire thing into a string """
    with open(filename, encoding='utf-8') as file:
        return file.read()


def read_icon(filename):
    """ Given a filename, read the data into a string from the icons directory """
    return read_file(os.path.join(os.path.dirname(__file__), 'icons', filename))


def request_url(url: str,
                client_id: Optional[str] = None,
                timeout: int = 30) -> typing.Optional[requests.Response]:
    """ Requests a URL, attempting to canonicize it as it goes """

    for prefix in ('', 'https://', 'http://'):
        attempt = prefix + url
        try:
            return requests.get(attempt, headers={
                'User-Agent': get_user_agent(client_id)
            },
                timeout=timeout
            )
        except requests.exceptions.MissingSchema:
            LOGGER.info("Missing schema on URL %s", attempt)
        except requests.exceptions.InvalidSchema:
            LOGGER.info("Unsupported schema on URL %s", attempt)
            return None
        except Exception as err:  # pylint:disable=broad-except
            LOGGER.info("%s failed: %s", attempt, err)

    return None


def resolve_value(val):
    """ if given a callable, call it; otherwise, return it """
    if callable(val):
        return val()
    return val


def permanent_url(response: requests.Response) -> str:
    """ Given a requests.Response object, determine what the permanent URL
    for it is from the response history """

    def normalize(url):
        # normalize the netloc to lowercase
        parsed = urllib.parse.urlparse(url)
        return urllib.parse.urlunparse(parsed._replace(netloc=parsed.netloc.lower()))

    for item in response.history:
        if item.status_code in (301, 308):
            # permanent redirect means we continue on to the next URL in the
            # redirection change
            continue
        # Any other status code is assumed to be a temporary redirect, so this
        # is the last permanent URL
        return normalize(item.url)

    # Last history item was a permanent redirect, or there was no history
    return normalize(response.url)


def pkce_challenge(verifier: str, method: str = 'S256') -> str:
    """ Convert a PKCE verifier string to a challenge string

    See RFC 7636 """

    if method == 'plain':
        return verifier

    if method == 'S256':
        hashed = hashlib.sha256(verifier.encode()).digest()
        encoded = base64.urlsafe_b64encode(hashed)
        return encoded.decode().strip('=')

    raise ValueError(f'Unknown PKCE method {method}')


def extract_rel(rel: str, base_url, content, links) -> typing.Set[str]:
    """ Given a parsed page/response, extract all of the URLs that match a particular link rel """
    result: typing.Set[str] = set()

    if links and rel in links:
        LOGGER.debug("%s: Found %s link header: %s", base_url, rel, links[rel]['url'])
        result.add(links[rel]['url'])

    if content:
        for link in content.find_all(('link', 'a'), rel=rel):
            LOGGER.debug("%s: Found %s link tag: %s", base_url, rel, link.get('href'))
            result.add(urllib.parse.urljoin(base_url, link.get('href')))

    return result
