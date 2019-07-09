
""" Basis for Authl authentication handlers """

from abc import ABC, abstractmethod, abstractproperty


class Handler(ABC):
    """ base class for authentication handlers """

    @abstractmethod
    def handles_url(self, url):
        """ Returns True if we can handle this URL, by pattern match """

    @abstractmethod
    def handles_page(self, headers, content, links):
        """ Returns True if we can handle the page based on page content

        headers -- the raw headers from the page request, as a MultiDict (as
            provided by the requests library)
        content -- the page content, as a BeautifulSoup4 parse tree
        links -- the results of parsing the Link: headers, as a dict of
            rel -> list of href/rel pairs (as provided by the requests library)
        """

    @abstractmethod
    def initiate_auth(self, id_url, callback_url):
        """ Initiates a remote auth request for the URL, with the specified
        return URL.

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

    @abstractproperty
    def service_name(self):
        """ Returns the human-readable service name """

    @abstractproperty
    def url_schemes(self):
        """ Returns a list of supported URL schemes for the login UI to fill in
        with a placeholder.

        Format is a list of tuples of (format, default_placeholder) where the
        format string contains a '%' which indicates where the placeholder goes.
        """

    @abstractproperty
    def description(self):
        """ Returns a description of the service. HTML, I guess. """
