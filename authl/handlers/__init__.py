
""" Basis for Authl authentication handlers """

import typing
from abc import ABC, abstractmethod

from .. import disposition


class Handler(ABC):
    """ base class for authentication handlers """

    def handles_url(self, url: str) -> typing.Union[str, bool]:
        """
        If this handler can handle this URL (or something that looks like it),
        return something truthy, e.g. a canonicized version of the URL.
        Otherwise, return False.

        It is okay to check for an API endpoint in implementing this. However,
        if the content kept at the URL itself needs to be parsed to make the
        determination, implement that in handles_page instead.

        Whatever value this returns will be passed back in to initiate_auth, so
        if that value matters, return a reasonable URL.
        """
        # pylint:disable=no-self-use,unused-argument
        return False

    def handles_page(self, url: str, headers, content, links) -> bool:
        """ Returns True if we can handle the page based on page content

        url -- the canonicized identity URL
        headers -- the raw headers from the page request, as a MultiDict (as
            provided by the requests library)
        content -- the page content, as a BeautifulSoup4 parse tree
        links -- the results of parsing the Link: headers, as a dict of
            rel -> dict of 'url' and 'rel', as provided by the Requests library
        """
        # pylint:disable=no-self-use,unused-argument
        return False

    @property
    @abstractmethod
    def cb_id(self) -> str:
        """ Gets the callback ID for callback registration. Must be unique,
        and should be short and stable. """

    @abstractmethod
    def initiate_auth(self, id_url: str, callback_uri: str, redir: str) -> disposition.Disposition:
        """ Initiates a remote auth request

        :param str id_url: Canonicized identity URL
        :param str callback_uri: Callback URL for verification
        :param str redir: Where to redirect the user to after verification

        Returns a Disposition object to be handled by the frontend.
        """

    @abstractmethod
    def check_callback(self, url: str, get, data) -> disposition.Disposition:
        """ Checks the authorization of an incoming verification from the client.

        Params:
            url -- the full URL of the verification
            get -- the GET parameters for the verification
            data -- the POST parameters for the verification

        Returns a Disposition object to be handled by the frontend.
        """

    @property
    @abstractmethod
    def service_name(self) -> str:
        """ Returns the human-readable service name """

    @property
    @abstractmethod
    def url_schemes(self) -> typing.List[typing.Tuple[str, str]]:
        """ Returns a list of supported URL schemes for the login UI to fill in
        with a placeholder.

        Format is a list of tuples of (format, default_placeholder) where the
        format string contains a '%' which indicates where the placeholder goes.
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """ Returns a description of the service, in HTML format. """
