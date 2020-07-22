""" Webfinger functions """

import html
import logging
import re
import typing

import requests

LOGGER = logging.getLogger(__name__)


def get_profiles(url: str) -> typing.Set[str]:
    """ Get the potential profile page URLs from a webfinger query """
    webfinger = re.match(r'@([^@]+)@(.*)$', url)
    if not webfinger:
        return set()

    try:
        user, domain = webfinger.group(1, 2)
        LOGGER.debug("webfinger: user=%s domain=%s", user, domain)

        resource = html.escape(f'acct:{user}@{domain}')
        request = requests.get(f'https://{domain}/.well-known/webfinger?resource={resource}')

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
        LOGGER.exception("Failed to decode %s profile", resource)
        return set()
