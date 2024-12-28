"""
Authl instance
==============

An :py:class:`Authl` instance acts as the initial coordinator between the
configured :py:class:`handler.Handler` instances; given an identity address
(such as an email address, WebFinger address, or Internet URL) it looks up the
appropriate handler to use to initiate the login transaction, and it will also
look up the handler for a transaction in progress.

"""

import collections
import logging
import typing
from typing import Optional

import expiringdict
from bs4 import BeautifulSoup

from . import handlers, tokens, utils, webfinger

LOGGER = logging.getLogger(__name__)


class Authl:
    """ The authentication wrapper instance.

    :param cfg_handlers: The list of configured handlers, in decreasing priority
        order.

    """

    def __init__(self, cfg_handlers: Optional[typing.List[handlers.Handler]] = None):
        """ Initialize an Authl library instance. """
        self._handlers: typing.Dict[str, handlers.Handler] = collections.OrderedDict()
        if cfg_handlers:
            for handler in cfg_handlers:
                self.add_handler(handler)

    def add_handler(self, handler: handlers.Handler):
        """
        Adds another handler to the configured handler list at the lowest priority.
        """
        cb_id = handler.cb_id
        if cb_id in self._handlers:
            raise ValueError("Already have handler with id " + cb_id)
        self._handlers[cb_id] = handler

    def _match_url(self, url: str):
        for hid, handler in self._handlers.items():
            result = handler.handles_url(url)
            if result:
                LOGGER.debug("%s URL matches %s", url, handler)
                return handler, hid, result
        return None, None, None

    def get_handler_for_url(self, url: str) -> typing.Tuple[typing.Optional[handlers.Handler],
                                                            str,
                                                            str]:
        """

        Get the appropriate handler for the specified identity address. If
        more than one handler knows how to handle an address, it will use the
        one with the highest priority.

        :param str url: The identity address; typically a URL but can also be a
            WebFinger or email address.

        :returns: a tuple of ``(handler, hander_id, profile_url)``.

        """
        # pylint:disable=too-many-return-statements

        url = url.strip()
        if not url:
            return None, '', ''

        # check webfinger profiles
        resp = self.check_profiles(webfinger.get_profiles(url))
        if resp and resp[0]:
            return resp

        by_url = self._match_url(url)
        if by_url[0]:
            return by_url

        request = utils.request_url(url)
        if request:
            profile = utils.permanent_url(request)
            if profile != url:
                LOGGER.debug("%s: got permanent redirect to %s", url, profile)
                # the profile URL is different than the request URL, so re-run
                # the URL matching logic just in case
                by_url = self._match_url(profile)
                if by_url[0]:
                    return by_url

            soup = BeautifulSoup(request.text, 'html.parser')
            for hid, handler in self._handlers.items():
                if handler.handles_page(profile, request.headers, soup, request.links):
                    LOGGER.debug("%s response matches %s", profile, handler)
                    return handler, hid, request.url

            # check for RelMeAuth candidates
            resp = self.check_profiles(utils.extract_rel('me', profile, soup, request.links))
            if resp and resp[0]:
                return resp

        LOGGER.debug("No handler found for URL %s", url)
        return None, '', ''

    def get_handler_by_id(self, handler_id):
        """ Get the handler with the given ID, for a transaction in progress. """
        return self._handlers.get(handler_id)

    def check_profiles(self, profiles) -> typing.Tuple[typing.Optional[handlers.Handler], str, str]:
        """ Given a list of profile URLs, check them for a handle-able identity """
        for profile in profiles:
            LOGGER.debug("Checking profile %s", profile)
            resp = self.get_handler_for_url(profile)
            if resp and resp[0]:
                return resp

        return None, '', ''

    @property
    def handlers(self):
        """ Provides a list of all of the registered handlers. """
        return self._handlers.values()


def from_config(config: typing.Dict[str, typing.Any],
                state_storage: Optional[dict] = None,
                token_storage: Optional[tokens.TokenStore] = None) -> Authl:
    """ Generate an Authl handler set from provided configuration directives.

    :param dict config: a configuration dictionary. See the individual handlers'
        from_config functions to see possible configuration values.

    :param dict state_storage: a dict-like object that will store session
        state for methods that need it. Defaults to an instance-local
        ExpiringDict; this will not work well in load-balanced scenarios. This
        can be safely stored in a user session, if available.

    :param tokens.TokenStore token_storage: a TokenStore for storing session
        state for methods that need it. Defaults to an instance-local DictStore
        backed by an ExpiringDict; this will not work well in load-balanced
        scenarios.

    Handlers will be enabled based on truthy values of the following keys:

    * ``EMAIL_FROM`` / ``EMAIL_SENDMAIL``: enable :py:mod:`authl.handlers.email_addr`

    * ``FEDIVERSE_NAME``: enable :py:mod:`authl.handlers.fediverse`

    * ``INDIEAUTH_CLIENT_ID``: enable :py:mod:`authl.handlers.indieauth`

    * ``TEST_ENABLED``: enable :py:mod:`authl.handlers.test_handler`

    For additional configuration settings, see each handler's respective
    ``from_config()``.

    """

    if token_storage is None:
        token_storage = tokens.DictStore()

    if state_storage is None:
        state_storage = expiringdict.ExpiringDict(max_len=1024, max_age_seconds=3600)

    instance = Authl()

    if config.get('EMAIL_FROM') or config.get('EMAIL_SENDMAIL'):
        from .handlers import email_addr
        instance.add_handler(email_addr.from_config(config, token_storage))

    if config.get('INDIEAUTH_CLIENT_ID'):
        from .handlers import indieauth
        instance.add_handler(indieauth.from_config(config, token_storage))

    if config.get('FEDIVERSE_NAME') or config.get('MASTODON_NAME'):
        from .handlers import fediverse
        instance.add_handler(fediverse.from_config(config, token_storage))

    if config.get('TEST_ENABLED'):
        from .handlers import test_handler
        instance.add_handler(test_handler.TestHandler())

    return instance
