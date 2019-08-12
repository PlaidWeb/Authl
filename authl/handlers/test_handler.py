""" Test handler which always returns an immediate success. Not to be used
in production. """

from .. import disposition
from . import Handler


class TestHandler(Handler):
    """ An Authl handler which always returns True for any URI beginning with
    'test:'. Primarily for testing purposes. """

    def handles_url(self, url):
        if url.startswith('test:'):
            return url
        return None

    def initiate_auth(self, id_url, callback_url):
        return disposition.Verified(id_url)

    def check_callback(self, url, get, data):
        return disposition.Error("This shouldn't be possible")

    @property
    def service_name(self):
        return 'Loopback'

    @property
    def url_schemes(self):
        return [('test:%', 'example')]

    @property
    def description(self):
        return """Used for testing purposes. Don't use this on a production website."""
