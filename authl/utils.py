""" Utility functions """

import logging
import os.path
import typing
import urllib.parse

import requests

LOGGER = logging.getLogger(__name__)


def read_file(filename):
    """ Given a filename, read the entire thing into a string """
    with open(filename, encoding='utf-8') as file:
        return file.read()


def read_icon(filename):
    """ Given a filename, read the data into a string from the icons directory """
    return read_file(os.path.join(os.path.dirname(__file__), 'icons', filename))


def request_url(url: str) -> typing.Optional[requests.Response]:
    """ Requests a URL, attempting to canonicize it as it goes """

    for prefix in ('', 'https://', 'http://'):
        attempt = prefix + url
        try:
            return requests.get(attempt)
        except requests.exceptions.MissingSchema:
            LOGGER.info("Missing schema on URL %s", attempt)
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
