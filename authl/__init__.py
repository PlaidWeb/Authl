import requests


class Authl:
    """ Authentication wrapper """

    def __init__(self, handlers=None):
        self._handlers = handlers or []
        self._handler_map = {id(handler): handler for handler in self._handlers}

    def add_handler(self, handler):
        self.handlers.append(handler)
        self._handler_map[id(handler)] = handler

    def get_handler_for_url(self, url):
        for h in handlers:
            if h.handles_url(url):
                return h

        request = requests.get(url)
        for h in handlers:
            if h.handles_page(request.headers, request.text):
                return h

        return None

    def get_handler(self, handler_id):
        return self._handler_map.get(handler_id)

    @property
    def handlers(self):
        return [*self.handlers]
