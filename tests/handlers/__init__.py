""" test functions for the handler tests """

import urllib.parse


def parse_args(url):
    """ parse query parameters from a callback URL """
    url = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(url.query)
    return {key: val[0] for key, val in params.items()}
