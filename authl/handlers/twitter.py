"""
Twitter
=======

This handler allows third-party login using `Twitter <https://twitter.com/>`_.
To use it you will need to register your website as an application via the
`Twitter developer portal <https://developer.twitter.com/en>`_ and retrieve your
``client_key`` and ``client_secret`` from there. You will also need to register
your website's Twitter callback handler(s). Remember to include all URLs that
the callback might be accessed from, including test domains.

It is **highly recommended** that you only store the ``client_key`` and
``client_secret`` in an environment variable rather than by checked-in code, as
a basic security precaution against credential leaks.

See :py:func:`from_config` for the simplest configuration mechanism.

"""

import logging
import re
import time
import urllib.parse

import expiringdict
import requests
from requests_oauthlib import OAuth1, OAuth1Session

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


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
        # pylint:disable=too-many-arguments
        self._client_key = client_key
        self._client_secret = client_secret
        self._timeout = timeout or 600
        self._pending = expiringdict.ExpiringDict(
            max_len=128,
            max_age_seconds=self._timeout) if storage is None else storage

    # regex to match a twitter URL and optionally extract the username
    twitter_regex = re.compile(r'(https?://)?[^/]*\.?twitter\.com/?@?([^?]*)')

    @staticmethod
    def handles_url(url):
        match = Twitter.twitter_regex.match(url)
        if match:
            return 'https://twitter.com/' + match.group(2)

        return None

    @property
    def cb_id(self):
        return 't'

    def initiate_auth(self, id_url, callback_uri, redir):
        match = Twitter.twitter_regex.match(id_url)
        if not match:
            return disposition.Error("Got invalid Twitter URL", redir)

        try:
            username = match.group(2)
            oauth_session = OAuth1Session(
                client_key=self._client_key,
                client_secret=self._client_secret,
                callback_uri=callback_uri)

            req = oauth_session.fetch_request_token('https://api.twitter.com/oauth/request_token')

            token = req.get('oauth_token')
            secret = req.get('oauth_token_secret')

            params = {
                'oauth_token': token,
            }
            if username:
                params['screen_name'] = username

            self._pending[token] = (secret, callback_uri, redir, time.time())

            return disposition.Redirect(
                'https://api.twitter.com/oauth/authorize?' + urllib.parse.urlencode(params))
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error(err, redir)

    def check_callback(self, url, get, data):
        if 'denied' in get:
            token = get['denied']
        elif 'oauth_token' in get:
            token = get['oauth_token']
        if not token or token not in self._pending:
            return disposition.Error("Invalid transaction", '')

        secret, callback_uri, redir, start_time = self._pending.pop(token)

        if time.time() > start_time + self._timeout:
            return disposition.Error("Login timed out", redir)

        if 'denied' in get or 'oauth_verifier' not in get:
            return disposition.Error("Twitter authorization declined", redir)

        auth = None

        try:
            oauth_session = OAuth1Session(
                client_key=self._client_key,
                client_secret=self._client_secret,
                resource_owner_key=token,
                resource_owner_secret=secret,
                callback_uri=callback_uri)

            oauth_session.parse_authorization_response(url)

            request = oauth_session.fetch_access_token('https://api.twitter.com/oauth/access_token')
            token = request.get('oauth_token')
            auth = OAuth1(
                client_key=self._client_key,
                client_secret=self._client_secret,
                resource_owner_key=token,
                resource_owner_secret=request.get('oauth_token_secret'))

            user_info = requests.get(
                'https://api.twitter.com/1.1/account/verify_credentials.json?skip_status=1',
                auth=auth).json()
            LOGGER.log(logging.WARNING if 'errors' in user_info else logging.NOTSET,
                       "User profile showed error: %s", user_info.get('errors'))
            return disposition.Verified(
                # We include the user ID after the hash code to prevent folks from
                # logging in by taking over a username that someone changed/abandoned.
                f'https://twitter.com/{user_info["screen_name"]}#{user_info["id_str"]}',
                redir,
                self.build_profile(user_info))
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error(str(err), redir)
        finally:
            if auth:
                # let's clean up after ourselves
                request = requests.post('https://api.twitter.com/1.1/oauth/invalidate_token.json',
                                        auth=auth)
                LOGGER.debug("Token revocation request: %d %s", request.status_code, request.text)

    @property
    def generic_url(self):
        return 'https://twitter.com/'

    @staticmethod
    def build_profile(user_info: dict) -> dict:
        """ Convert a Twitter userinfo JSON into an Authl profile """
        entities = user_info.get('entities', {})

        def expand_entities(name):
            text = user_info[name]
            for url in entities.get(name, {}).get('urls', []):
                tco = url.get('url')
                real = url.get('expanded_url')
                if tco and real:
                    text = text.replace(tco, real)
            return text

        mapping = (('avatar', 'profile_image_url_https'),
                   ('bio', 'description'),
                   ('email', 'email'),
                   ('homepage', 'url'),
                   ('location', 'location'),
                   ('name', 'name'),
                   )
        profile = {p_key: expand_entities(t_key)
                   for p_key, t_key in mapping if t_key in user_info}

        # attempt to get a more suitable image
        if 'avatar' in profile:
            for rendition in ('_400x400', ''):
                req = requests.head(profile['avatar'].replace('_normal', rendition))
                if 200 <= req.status_code < 300:
                    LOGGER.info("Found better avatar rendition: %s", req.url)
                    profile['avatar'] = req.url
                    break

        return {k: v for k, v in profile.items() if v}


def from_config(config, storage):
    """ Generate a Twitter handler from the given config dictionary.

    Posible configuration values:

    * ``TWITTER_CLIENT_KEY``: The Twitter app's client_key

    * ``TWITTER_CLIENT_SECRET``: The Twitter app's client_secret

    * ``TWITTER_TIMEOUT``: How long to wait for the user to log in

    It is ***HIGHLY RECOMMENDED*** that the client key and secret be provided
    via environment variables or some other mechanism that doesn't involve
    checking these values into source control and exposing them on the
    file system.
    """

    return Twitter(config['TWITTER_CLIENT_KEY'],
                   config['TWITTER_CLIENT_SECRET'],
                   config.get('TWITTER_TIMEOUT'),
                   storage)
