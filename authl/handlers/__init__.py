
""" Basis for Authl authentication handlers """

from abc import ABC, abstractmethod


class Handler(ABC):
    """ base class for authentication handlers """

    def handles_url(self, url):
        """ Returns True if we can handle this URL, by pattern match """
        # pylint:disable=no-self-use,unused-argument
        return False

    def handles_page(self, url, headers, content, links):
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

    @abstractmethod
    def initiate_auth(self, id_url, callback_url):
        """ Initiates a remote auth request

        :param str id_url: Canonicized identity URL
        :param str callback_url: Callback URL for verification

        Returns a Disposition object to be handled by the frontend.
        """

    @abstractmethod
    def check_callback(self, url, get, data):
        """ Checks the authorization of an incoming verification from the client.

        Params:
            url -- the full URL of the verification
            get -- the GET parameters for the verification
            data -- the POST parameters for the verification

        Returns a Disposition object to be handled by the frontend.
        """

    @property
    @abstractmethod
    def service_name(self):
        """ Returns the human-readable service name """

    @property
    @abstractmethod
    def url_schemes(self):
        """ Returns a list of supported URL schemes for the login UI to fill in
        with a placeholder.

        Format is a list of tuples of (format, default_placeholder) where the
        format string contains a '%' which indicates where the placeholder goes.
        """

    @property
    @abstractmethod
    def description(self):
        """ Returns a description of the service. HTML, I guess. """
