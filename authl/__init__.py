import requests

from . import handlers


class UnhandledHandler(handlers.Handler):
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
        self._handlers = handlers or []

        self._unhandled = UnhandledHandler()

    def add_handler(self, handler):
        self._handlers.append(handler)
        self._handler_map[handler] = len(self._handlers)

    def get_handler_for_url(self, url):
        for pos, handler in enumerate(self._handlers):
            if handler.handles_url(url):
                return handler, pos

        request = requests.get(url)
        for pos, handler in enumerate(self._handlers):
            if handler.handles_page(request.headers, request.text):
                return handler, pos

        return self._unhandled, -1

    def get_handler(self, pos):
        return self._handlers[pos]
