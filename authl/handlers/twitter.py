"""
Twitter
=======

This handler allows third-party login using `Twitter <https://twitter.com/>`_.
To use it you will need to register your website as an application via the
`Twitter developer portal <https://developer.twitter.com/en>`_ and retrieve your
``client_key`` and ``client_secret`` from there. You will also need to register
your website's Twitter callback handler.

It is **highly recommended** that you only store the ``client_key`` and
``client_secret`` in an environment variable rather than by checked-in code as a
basic security precaution.

See :py:func:`from_config` for the simplest configuration mechanism.

"""

import re
import time
import urllib.parse

import expiringdict
import requests
from requests_oauthlib import OAuth1, OAuth1Session

from .. import disposition, utils
from . import Handler


class Twitter(Handler):
    """
    Twitter login handler.

    :param str client_key: The Twitter ``client_key`` value

    :param str client_secret: The Twitter ``client_secret`` value

    :param int timeout: How long, in seconds, the user has to complete the
        login

    :param dict storage: A ``dict``-like object that persistently stores the
        OAuth token and secret during the login transaction. This needs to
        persist on at least a per-user basis. It is safe to use the user session
        or browser cookies for this storage.

    """

    @property
    def description(self):
        return """Allows users to log on via <a href="https://twitter.com/">Twitter</a>."""

    @property
    def service_name(self):
        return "Twitter"

    @property
    def url_schemes(self):
        return [('https://twitter.com/%', 'username')]

    @property
    def logo_html(self):
        return [(utils.read_icon("twitter.svg"), 'Twitter')]

    def __init__(self, client_key: str,
                 client_secret: str,
                 timeout: int = None,
                 storage: dict = None):
        self._client_key = client_key
        self._client_secret = client_secret
        self._pending = expiringdict.ExpiringDict(
            max_len=128,
            max_age_seconds=timeout) if storage is None else storage
        self._timeout = timeout or 600

    # regex to match a twitter URL and optionally extract the username
    twitter_regex = re.compile(r'(https?://)?[^/]*\.?twitter\.com/?@?([^?]*)')

    @staticmethod
    def handles_url(url):
        match = Twitter.twitter_regex.match(url)
        if match:
            return 'https://twitter.com/' + match.group(2)

        return False

    @property
    def cb_id(self):
        return 't'

    def initiate_auth(self, id_url, callback_uri, redir):
        match = Twitter.twitter_regex.match(id_url)
        if not match:
            return disposition.Error("Got invalid Twitter URL", redir)

        username = match.group(2)
        oauth_session = OAuth1Session(
            client_key=self._client_key,
            client_secret=self._client_secret,
            callback_uri=callback_uri)

        req = oauth_session.fetch_request_token('https://api.twitter.com/oauth/request_token')

        token = req.get('oauth_token')
        params = {
            'oauth_token': token,
            'oauth_token_secret': req.get('oauth_token_secret')
        }
        if username:
            params['screen_name'] = username

        self._pending[token] = (params, callback_uri, redir, time.time())

        return disposition.Redirect(
            'https://api.twitter.com/oauth/authorize?' + urllib.parse.urlencode(params))

    def check_callback(self, url, get, data):
        if 'denied' in get:
            token = get['denied']
        elif 'oauth_token' in get:
            token = get['oauth_token']
        if not token or token not in self._pending:
            return disposition.Error("Invalid transaction", '')

        try:
            params, callback_uri, redir, start_time = self._pending.pop(token)
        except ValueError:
            return disposition.Error("Invalid token", '')

        if time.time() > start_time + self._timeout:
            return disposition.Error("Login timed out", redir)

        if 'denied' in get or 'oauth_verifier' not in get:
            return disposition.Error("Twitter authorization declined", redir)

        oauth_session = OAuth1Session(
            client_key=self._client_key,
            client_secret=self._client_secret,
            resource_owner_key=params['oauth_token'],
            resource_owner_secret=params['oauth_token_secret'],
            callback_uri=callback_uri)

        oauth_session.parse_authorization_response(url)

        request = oauth_session.fetch_access_token('https://api.twitter.com/oauth/access_token')
        auth = OAuth1(
            client_key=self._client_key,
            client_secret=self._client_secret,
            resource_owner_key=request.get('oauth_token'),
            resource_owner_secret=request.get('oauth_token_secret'))

        user_info = requests.get(
            'https://api.twitter.com/1.1/account/verify_credentials.json', auth=auth).json()
        if 'errors' in user_info:
            return disposition.Error(
                "Could not retrieve credentials: %r" % user_info.get('errors'),
                redir)

        user_id = user_info.get('id_str')
        username = user_info.get('screen_name')
        # We include the user ID after the hash code to prevent folks from
        # logging in by taking over a username that someone changed/abandoned.
        return disposition.Verified(
            f'https://twitter.com/{username}#{user_id}',
            redir,
            user_info)

    @property
    def generic_url(self):
        return 'https://twitter.com/'


def from_config(config, storage):
    """ Generate a Twitter handler from the given config dictionary.

    Posible configuration values:

    TWITTER_CLIENT_KEY -- The Twitter app's client_key
    TWITTER_CLIENT_SECRET -- The Twitter app's client_secret
    TWITTER_TIMEOUT -- How long to wait for the user to log in

    It is ***HIGHLY RECOMMENDED*** that the client key and secret be provided
    via environment variables or some other mechanism that doesn't involve
    checking these values into source control and exposing them on the
    file system.
    """

    return Twitter(config['TWITTER_CLIENT_KEY'],
                   config['TWITTER_CLIENT_SECRET'],
                   config.get('TWITTER_TIMEOUT'),
                   storage)
