""" Authl: A wrapper library to simplify the implementation of federated identity """

import collections
import logging
import typing

import itsdangerous
from bs4 import BeautifulSoup

from . import handlers, utils

LOGGER = logging.getLogger(__name__)


class Authl:
    """ Authentication wrapper """

    def __init__(self, cfg_handlers: typing.List[handlers.Handler] = None):
        """ Initialize an Authl library instance.

        :param cfg_handlers: a collection of handlers for different authentication
            mechanisms

        """
        self._handlers: typing.Dict[str, handlers.Handler] = collections.OrderedDict()
        if cfg_handlers:
            for handler in cfg_handlers:
                self.add_handler(handler)

    def add_handler(self, handler):
        """ Add another handler to the configured handler list. It will be
        given the lowest priority. """
        cb_id = handler.cb_id
        if cb_id in self._handlers:
            raise ValueError("Already have handler with id " + cb_id)
        self._handlers[cb_id] = handler

    def get_handler_for_url(self, url: str) -> typing.Tuple[typing.Optional[handlers.Handler],
                                                            str,
                                                            str]:
        """ Get the appropriate handler for the specified identity address.
        Returns a tuple of (handler, hander_id, profile_id). """

        # If webfinger detects profiles for this address, try all of those first
        for profile in utils.get_webfinger_profiles(url):
            LOGGER.debug("Checking profile %s", profile)
            resp = self.get_handler_for_url(profile)
            if resp[0]:
                return resp

        if not url:
            return None, '', ''

        for hid, handler in self._handlers.items():
            result = handler.handles_url(url)
            if result:
                LOGGER.debug("%s URL matches %s", url, handler)
                return handler, hid, result

        request = utils.request_url(url)
        if request:
            soup = BeautifulSoup(request.text, 'html.parser')
            for hid, handler in self._handlers.items():
                if handler.handles_page(request.url, request.headers, soup, request.links):
                    LOGGER.debug("%s response matches %s", request.url, handler)
                    return handler, hid, request.url

        LOGGER.debug("No handler found for URL %s", url)
        return None, '', ''

    def get_handler_by_id(self, handler_id):
        """ Get the handler with the given ID """
        return self._handlers.get(handler_id)

    @property
    def handlers(self):
        """ get all of the registered handlers, for UX purposes """
        return self._handlers.values()


def from_config(config: typing.Dict[str, typing.Any],
                secret_key: typing.Union[str, bytes],
                state_storage: dict = None) -> Authl:
    """ Generate an Authl handler set from provided configuration directives.

    Arguments:

    :param dict config: a configuration dictionary. See the individual handlers'
        from_config functions to see possible configuration values.
    :param std secret_key: a signing key used to keep authentication secrets.
    :param dict state_storage: a dict-like object that will store persistent
        state for methods that need it

    Handlers will be enabled based on truthy values of the following keys

        EMAIL_FROM / EMAIL_SENDMAIL -- enable the EmailAddress handler
        MASTODON_NAME -- enable the Mastodon handler
        INDIEAUTH_CLIENT_ID -- enable the IndieAuth handler
        INDIELOGIN_CLIENT_ID -- enable the IndieLogin handler
        TWITTER_CLIENT_KEY -- enable the Twitter handler
        TEST_ENABLED -- enable the test/loopback handler

    """

    serializer = itsdangerous.URLSafeTimedSerializer(secret_key)
    instance = Authl()

    if config.get('EMAIL_FROM') or config.get('EMAIL_SENDMAIL'):
        from .handlers import email_addr
        instance.add_handler(email_addr.from_config(config, serializer))

    if config.get('FEDIVERSE_NAME') or config.get('MASTODON_NAME'):
        from .handlers import fediverse
        instance.add_handler(fediverse.from_config(config, serializer))

    if config.get('INDIEAUTH_CLIENT_ID'):
        from .handlers import indieauth
        instance.add_handler(indieauth.from_config(config, serializer))

    if config.get('INDIELOGIN_CLIENT_ID'):
        from .handlers import indielogin
        instance.add_handler(indielogin.from_config(config, serializer))

    if config.get('TWITTER_CLIENT_KEY'):
        from .handlers import twitter
        instance.add_handler(twitter.from_config(config, state_storage))

    if config.get('TEST_ENABLED'):
        from .handlers import test_handler
        instance.add_handler(test_handler.TestHandler())

    return instance
