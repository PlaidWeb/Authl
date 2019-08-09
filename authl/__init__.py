""" Authl: A wrapper library to simplify the implementation of federated identity """

import logging
import re
import json
import html

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)


class Authl:
    """ Authentication wrapper """

    def __init__(self, handlers=None):
        """ Initialize an Authl library instance.

        handlers -- a collection of handlers for different authentication
            mechanisms

        """
        self._handlers = handlers or []

    def add_handler(self, handler):
        """ Add another handler to the configured handler list. It will be
        given the lowest priority. """
        self._handlers.append(handler)

    def get_handler_for_url(self, url):
        """ Get the appropriate handler for the specified identity URL.
        Returns a tuple of (handler, id, url). """
        for pos, handler in enumerate(self._handlers):
            result = handler.handles_url(url)
            if result:
                LOGGER.debug("%s URL matches %s", url, handler)
                return handler, pos, result

        request = request_url(url)
        if request:
            soup = BeautifulSoup(request.text, 'html.parser')
            for pos, handler in enumerate(self._handlers):
                if handler.handles_page(request.headers, soup, request.links):
                    LOGGER.debug("%s response matches %s", request.url, handler)
                    return handler, pos, request.url

        LOGGER.debug("No handler found for URL %s", url)
        return None, None, None

    def get_handler_by_id(self, handler_id):
        """ Get the handler with the given ID """
        return self._handlers[handler_id]

    @property
    def handlers(self):
        """ get all of the registered handlers, for UX purposes """
        return [*self._handlers]

def get_webfinger_profile(user, domain):
    """ Get the webfinger profile page URL from a webfinger query """
    resource = 'https://{}/.well-known/webfinger?resource={}'.format(domain,
        html.escape('acct:{}@{}'.format(user, domain)))
    request = requests.get(resource)

    if not 200 <= request.status_code < 300:
        LOGGER.info("Webfinger query %s returned status code %d", resource, request.status_code)
        LOGGER.debug("%s", request.text)
        return None

    try:
        profile = json.loads(request.text)
    except json.JSONDecodeError as err:
        LOGGER.info("Profile decode of %s failed: %s", resource, err)
        return None

    try:
        for link in profile['links']:
            if link['rel'] == 'http://webfinger.net/rel/profile-page':
                return link['href']
    except Exception as err: #pylint:disable=broad-except
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
        url = get_webfinger_profile(webfinger.group(1),webfinger.group(2))
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


def from_config(config, secret_key):
    """ Generate an AUthl handler set from provided configuration directives.

    Arguments:

    config -- a configuration dictionary. See the individual handlers'
        from_config functions to see possible configuration values.
    secret_key -- a signing key to use for the handlers which need one

    Handlers will be enabled based on truthy values of the following keys

        TEST_ENABLED -- enable the TestHandler handler
        EMAIL_FROM -- enable the EmailAddress handler
        INDIELOGIN_CLIENT_ID -- enable the IndieLogin handler

    """
    # pylint:disable=unused-argument

    handlers = []
    if config.get('EMAIL_FROM') or config.get('EMAIL_SENDMAIL'):
        from .handlers import email_addr

        handlers.append(email_addr.from_config(config))

    if config.get('MASTODON_NAME'):
        from .handlers import mastodon

        handlers.append(mastodon.from_config(config))

    if config.get('INDIELOGIN_CLIENT_ID'):
        from .handlers import indielogin

        handlers.append(indielogin.from_config(config))

    if config.get('TEST_ENABLED'):
        from .handlers import test_handler

        handlers.append(test_handler.TestHandler())

    return Authl(handlers)
