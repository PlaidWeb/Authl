"""
Webfinger utility
=================
"""

import html
import logging
import re
import typing

import requests

from . import utils

LOGGER = logging.getLogger(__name__)


def get_profiles(url: str, timeout: int = 30) -> typing.Set[str]:
    """

    Get the potential identity URLs from a webfinger address.

    :param str url: The webfinger URL

    :returns: A :py:type:`set` of potential identity URLs

    """
    webfinger = re.match(r'(@|acct:)([^@]+)@(.*)$', url)
    if not webfinger:
        return set()

    try:
        user, domain = webfinger.group(2, 3)
        LOGGER.debug("webfinger: user=%s domain=%s", user, domain)

        resource = html.escape(f'acct:{user}@{domain}')
        request = requests.get(f'https://{domain}/.well-known/webfinger?resource={resource}',
                               headers={'User-Agent': utils.USER_AGENT},
                               timeout=timeout)

        if not 200 <= request.status_code < 300:
            LOGGER.info("Webfinger query %s returned status code %d",
                        resource, request.status_code)
            LOGGER.debug("%s", request.text)
            # Service doesn't support webfinger, so just pretend it's the most
            # common format for a profile page
            return {f'https://{domain}/@{user}'}

        profile = request.json()
        print(repr(profile))

        return {link['href'] for link in profile['links']
                if link['rel'] in ('http://webfinger.net/rel/profile-page', 'profile', 'self')}
    except Exception:  # pylint:disable=broad-except
        LOGGER.info("Failed to decode %s profile", resource)
        return set()
