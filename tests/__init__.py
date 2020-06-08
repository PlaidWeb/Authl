""" Common functions for the test routines """
import logging

from authl import handlers

logging.basicConfig(level=logging.DEBUG)


class TestHandler(handlers.Handler):
    """ null test handler that does nothing """

    @property
    def cb_id(self):
        return "nothing"

    def initiate_auth(self, id_url, callback_uri, redir):
        raise ValueError("not implemented")

    def check_callback(self, url, get, data):
        raise ValueError("not implemented")

    @property
    def service_name(self):
        return "Nothing"

    @property
    def url_schemes(self):
        return []

    @property
    def description(self):
        return "Does nothing"
