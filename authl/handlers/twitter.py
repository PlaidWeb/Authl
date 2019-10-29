""" Twitter login handler """

import re
import urllib.parse

import requests
from requests_oauthlib import OAuth1, OAuth1Session

from .. import disposition
from . import Handler


class Twitter(Handler):
    """ Twitter handler. Needs a client_key and client_secret. It is HIGHLY
    RECOMMENDED that these configuration parameters be provided via an
    environment variable rather than by checked-in code, as a basic security
    precaution. """

    @property
    def description(self):
        return """Allows users to log on via <a href="https://twitter.com/">Twitter</a>."""

    @property
    def service_name(self):
        return "Twitter"

    @property
    def url_schemes(self):
        return [('https://twitter.com/%', 'username')]

    def __init__(self, token_store, client_key, client_secret):
        self._client_key = client_key
        self._client_secret = client_secret
        self._pending = token_store

    # regex to match a twitter URL and optionally extract the username
    twitter_regex = re.compile(r'(https?://)?[^/]*\.?twitter\.com/?@?(.*)')

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

        self._pending[token] = (params, callback_uri, redir)

        return disposition.Redirect(
            'https://api.twitter.com/oauth/authorize?' + urllib.parse.urlencode(params))

    def check_callback(self, url, get, data):
        if 'denied' in get:
            return disposition.Error("Access denied", None)

        token = get.get('oauth_token')
        if not token:
            return disposition.Error("No transaction ID provided", None)
        if token not in self._pending:
            return disposition.Error("Transaction invalid or expired", None)

        params, callback_uri, redir = self._pending[token]
        del self._pending[token]

        if not get.get('oauth_verifier'):
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
            'https://twitter.com/{}#{}'.format(username, user_id),
            redir,
            user_info)


def from_config(config, token_store):
    """ Generate a Twitter handler from the given config dictionary.

    Posible configuration values:

    TWITTER_CLIENT_KEY -- The Twitter app's client_key
    TWITTER_CLIENT_SECRET -- The Twitter app's client_secret

    It is ***HIGHLY RECOMMENDED*** that these configuration values be provided
    via environment variables or some other mechanism that doesn't involve
    checking these values into source control and exposing them on the
    file system.
    """

    return Twitter(token_store, config['TWITTER_CLIENT_KEY'],
                   config['TWITTER_CLIENT_SECRET'])
