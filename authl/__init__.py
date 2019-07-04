""" Authl: A wrapper library to simplify the implementation of federated identity """

import requests

from .handlers import Handler
from . import disposition


class _UnhandledHandler(Handler):
    """ A Handler for unhandled URIs """

    def handles_url(self, url):
        return False

    def handles_page(self, headers, content):
        return False

    def initiate_auth(self, id_url, callback_url):
        return disposition.Error("Don't know how to handle " + id_url)

    def check_callback(self, url, get, data):
        raise NotImplementedError("this should never happen")

    def service_name(self):
        return None

    def url_scheme(self):
        return None


class Authl:
    """ Authentication wrapper """

    def __init__(self, handlers=None):
        """ Initialize an Authl library instance.

        handlers -- a collection of handlers for different authentication
            mechanisms

        """
        self._handlers = handlers or []
        self._unhandled = _UnhandledHandler()

    def add_handler(self, handler):
        """ Add another handler to the configured handler list. It will be
        given the lowest priority. """
        self._handlers.append(handler)

    def get_handler_for_url(self, url):
        """ Get the appropriate handler for the specified identity URL.
        Returns a tuple of (handler, id). """
        for pos, handler in enumerate(self._handlers):
            if handler.handles_url(url):
                return handler, pos

        request = requests.get(url)
        for pos, handler in enumerate(self._handlers):
            if handler.handles_page(request.headers, request.text):
                return handler, pos

        return self._unhandled, -1

    def get_handler_by_id(self, handler_id):
        """ Get the handler with the given ID """
        return self._handlers[handler_id]
