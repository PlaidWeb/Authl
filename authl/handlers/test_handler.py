""" Test handler which always returns an immediate success. Not to be used
in production. """

from . import Handler
from .. import disposition


class TestHandler(Handler):
    """ An Authl handler which always returns True for any URI beginning with
    'test:'. Primarily for testing purposes. """

    def handles_url(self, url):
        return url.startswith('test:')

    def handles_page(self, headers, content):
        return False

    def initiate_auth(self, id_url, callback_url):
        return disposition.Verified(id_url)

    def check_callback(self, url, get, data):
        return disposition.Error("This shouldn't be possible")

    def service_name(self):
        return 'Loopback'

    def url_scheme(self):
        return 'test:%', 'example'
