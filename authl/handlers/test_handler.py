"""
Test handler
============

This is a handler which always lets people log in as any URL with the fake
scheme of ``test:``, with the exception of ``test:error`` which generates an
error. This is only to be used for testing locally and should not be enabled in
production.

"""

from .. import disposition
from . import Handler


class TestHandler(Handler):
    """ An Authl handler which always returns True for any URI beginning with
    'test:'. Primarily for testing purposes. """

    def handles_url(self, url):
        """ Returns ``True`` if the URL starts with ``'test:'``. """
        if url.startswith('test:'):
            return url
        return None

    def initiate_auth(self, id_url, callback_uri, redir):
        """
        Immediately returns a :py:class:`disposition.Verified`, unless the URL
        is ``'test:error'`` in which case it returns a
        :py:class:`disposition.Error`.
        """
        if id_url == 'test:error':
            return disposition.Error("Error identity requested", redir)
        return disposition.Verified(id_url, redir)

    def check_callback(self, url, get, data):
        return disposition.Error("This shouldn't be possible", None)

    @property
    def cb_id(self):
        return 'TEST_DO_NOT_USE'

    @property
    def service_name(self):
        return 'Loopback'

    @property
    def url_schemes(self):
        return [('test:%', 'example')]

    @property
    def description(self):
        return """Used for testing purposes. Don't use this on a production website."""
