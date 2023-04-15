
"""
Base handler class
==================

The :py:class:`Handler` class defines the abstract interface for an
authentication handler. Handlers are registered to an :py:class:`authl.Authl`
instance which then selects the handler based on the provided identity.

The basic flow for how a handler is selected is:

#. The :py:class:`authl.Authl` instance checks to see if any handler knows how
   to handle the identity URL directly; if so, it returns the first match.

#. The instance retrieves the URL, and hands the parse tree and response headers
   off to each handler to see if it's able to handle the URL based on that; if
   so, it returns the first match.

In the case of a Webfinger address (e.g. ``@user@example.com``) it repeats this
process for every profile URL provided by the Webfinger response until it finds
a match.

"""

import typing
from abc import ABC, abstractmethod

from .. import disposition


class Handler(ABC):
    """ Base class for authentication handlers """

    def handles_url(self, url: str) -> typing.Optional[str]:
        """
        If this handler can handle this URL (or something that looks like it),
        return something truthy, e.g. a canonicized version of the URL.
        Otherwise, return None.

        It is okay to check for an API endpoint (relative to the URL) in
        implementing this. However, if the content kept at the URL itself needs
        to be parsed to make the determination, implement that in
        :py:meth:`handles_page` instead.

        Whatever value this returns will be passed back in to initiate_auth, so
        if that value matters, return a reasonable URL.
        """
        # pylint:disable=unused-argument
        return None

    def handles_page(self, url: str, headers, content, links) -> bool:
        """ Returns ``True``/truthy if we can handle the page based on page
        content

        :param str url: the canonicized identity URL
        :param dict headers: the raw headers from the page request, as a
            MultiDict (as provided by the `Requests`_ library)
        :param bs4.BeautifulSoup content: the page content, as a
            `BeautifulSoup4`_ parse tree
        :param dict links: the results of parsing the Link: headers, as a
            dict of rel -> dict of 'url' and 'rel', as provided by the
            `Requests`_ library

        .. _Requests: https://requests.readthedocs.io/
        .. _BeautifulSoup4: https://pypi.org/project/beautifulsoup4/
        """
        # pylint:disable=unused-argument
        return False

    @property
    @abstractmethod
    def cb_id(self) -> str:
        """ The callback ID for callback registration. Must be unique across all
        registered handlers, and should be short and stable.
        """

    @abstractmethod
    def initiate_auth(self, id_url: str, callback_uri: str, redir: str) -> disposition.Disposition:
        """ Initiates the authentication flow.

        :param str id_url: Canonicized identity URL
        :param str callback_uri: Callback URL for verification
        :param str redir: Where to redirect the user to after verification

        :returns: the :py:mod:`authl.disposition` to be handled by the frontend.

        """

    @abstractmethod
    def check_callback(self, url: str, get: dict, data: dict) -> disposition.Disposition:
        """ Checks the authorization callback sent by the external provider.

        :param str url: the full URL of the verification request
        :param dict get: the GET parameters for the verification
        :param dict data: the POST parameters for the verification

        :returns: a :py:mod:`authl.disposition` object to be handled by the
            frontend. Any errors which get raised internally should be caught and
            returned as an appropriate :py:class:`authl.disposition.Error`.

        """

    @property
    @abstractmethod
    def service_name(self) -> str:
        """ The human-readable service name """

    @property
    @abstractmethod
    def url_schemes(self) -> typing.List[typing.Tuple[str, str]]:
        """
        A list of supported URL schemes for the login UI to fill in
        with a placeholder.

        The list is of tuples of ``(format, default_placeholder)``, where the
        format string contains a ``'%'`` indicating where the placeholder goes.
        """

    @property
    def generic_url(self) -> typing.Optional[str]:
        """
        A generic URL that can be used with this handler irrespective of
        identity.
        """
        return None

    @property
    @abstractmethod
    def description(self) -> str:
        """ A description of the service, in HTML format. """

    @property
    def logo_html(self) -> typing.Optional[str]:
        """ A list of tuples of (html,label) for the login buttons.

        The HTML should be an isolated ``<svg>`` element, or an ``<img src>``
        pointing to a publicly-usable ``https:`` URL.
        """
        return None
