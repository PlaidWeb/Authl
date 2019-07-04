
""" Basis for Authl authentication handlers """

from abc import ABC, abstractmethod, abstractproperty


class Handler(ABC):
    """ base class for all external auth providers """

    @abstractmethod
    def handles_url(self, url):
        """ Returns True if this handler can handle this URL
        e.g. a Twitter OAuth Handler would be configured to return True if it
        matches r'(https?://)twitter\\.com/(user/)?'
        """

    @abstractmethod
    def handles_page(self, headers, content):
        """ Returns True if this handler can handle the page based on headers
        e.g. a generic OpenID handler returns True if headers.links or the page
        links contain rel="openid.server"
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
    def url_scheme(self):
        """ Returns a URL scheme for the login UI to fill in with a placeholder.

        Format is a tuple, the first being an example URL with a % placeholder,
        the second being the text to put into the placeholder.

        Examples:

        ('http://twitter.com/%', 'username')  # Twitter
        ('https://%', 'instance/@username')   # Mastodon
        ('%', 'email@example.com')            # Email

        """
