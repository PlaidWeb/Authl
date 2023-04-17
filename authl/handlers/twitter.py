"""
Twitter
=======

This handler allows third-party login using `Twitter <https://twitter.com/>`_.
To use it you will need to register your website as an application via the
`Twitter developer portal <https://developer.twitter.com/en>`_ and retrieve your
``client_id`` and ``client_secret`` from there. You will also need to register
your website's Twitter callback handler(s). Remember to include all URLs that
the callback might be accessed from, including test domains.

It is **highly recommended** that you only store the ``client_id`` and
``client_secret`` in an environment variable rather than by checked-in code, as
a basic security precaution against credential leaks.

See :py:func:`authl.from_config` for the simplest configuration mechanism.

This handler registers itself with a ``cb_id`` of ``"t"``.

"""

import logging
import re
import time
import urllib.parse
import base64
import os
import hashlib
from typing import Optional

import expiringdict
import requests
from requests_oauthlib import OAuth2Session

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class Twitter(Handler):
    """
    Twitter login handler.

    :param str client_id: The Twitter ``client_id`` value

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

    def __init__(self, client_id: str,
                 client_secret: str,
                 timeout: Optional[int] = None,
                 storage: Optional[dict] = None):
        # pylint:disable=too-many-arguments
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout or 600
        self._pending = expiringdict.ExpiringDict(
            max_len=128,
            max_age_seconds=self._timeout) if storage is None else storage
        self._http_timeout = 30

    # regex to match a twitter URL and optionally extract the username
    twitter_regex = re.compile(r'(https?://)?[^/]*\.?twitter\.com/?@?([^?]*)')

    def handles_url(self, url):
        match = Twitter.twitter_regex.match(url)
        if match:
            return 'https://twitter.com/' + match.group(2)

        return None

    @property
    def cb_id(self):
        return 't'

    def get_client(self, callback_uri):
        return OAuth2Session(self._client_id,
                             redirect_uri=callback_uri,
                             scope=['tweet.read', 'users.read'])

    def initiate_auth(self, id_url, callback_uri, redir):
        match = Twitter.twitter_regex.match(id_url)
        if not match:
            return disposition.Error("Got invalid Twitter URL", redir)

        try:
            username = match.group(2)

            # Create a code verifier
            code_verifier = base64.urlsafe_b64encode(os.urandom(30)).decode("utf-8")
            code_verifier = re.sub("[^a-zA-Z0-9]+", "", code_verifier)

            # Create a code challenge
            code_challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
            code_challenge = base64.urlsafe_b64encode(code_challenge).decode("utf-8")
            code_challenge = code_challenge.replace("=", "")

            client = self.get_client(callback_uri)
            authorization_url, state = client.authorizaton_url(
                "https://twitter.com/i/oauth2/authorize",
                code_challenge=code_challenge,
                code_chalelnge_method="S256"
            )

            self._pending[state] = (callback_uri, redir, code_verifier, time.time())

            return disposition.Redirect(authorization_url)
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error(err, redir)

    def check_callback(self, url, get, data):
        code = get.get('code')
        if not code or code not in self._pending:
            return disposition.Error("Invalid transaction", '')

        callback_uri, redir, code_verifier, start_time = self._pending.pop(code)

        if time.time() > start_time + self._timeout:
            return disposition.Error("Login timed out", redir)

        client = self.get_client(callback_uri)

        try:
            token = client.fetch_token(
                token_url="https://api.twitter.com/2/oauth2/token",
                client_secret=self._client_secret,
                code_verifier=code_verifier,
                code=code)

            headers = {
                "Authorizaton": f"Bearer{token['access_token']}",
                "Content-Type": "application/json"
            }

            response = client.get("https://api.twitter.com/2/users/me", {
                "user.fields": ",".join("id",
                                        "name",
                                        "username",
                                        "description",
                                        "entities",
                                        "location",
                                        "profile_image_url",
                                        "url")
            }, headers=headers, timeout=self._http_timeout)

            user_info = response.json()
            LOGGER.debug("Got user info: %s", user_info)

            return disposition.Verified(
                f'https://twitter.com/i/user/{user_info["id_str"]}',
                redir,
                self.build_profile(user_info))
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error(str(err), redir)
        finally:
            if token:
                # let's clean up after ourselves
                request = requests.post('https://api.twitter.com/oauth2/invalidate_token',
                                        data={'access_token': token},
                                        headers=headers, timeout=self._http_timeout)
                LOGGER.debug("Token revocation request: %d %s", request.status_code, request.text)

    @property
    def generic_url(self):
        return 'https://twitter.com/'

    def build_profile(self, user_info: dict) -> dict:
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

        mapping = (('avatar', 'profile_image_url'),
                   ('bio', 'description'),
                   ('email', 'email'),
                   ('homepage', 'url'),
                   ('location', 'location'),
                   ('name', 'name'),
                   )
        profile = {p_key: expand_entities(t_key)
                   for p_key, t_key in mapping if t_key in user_info}

        profile['profile_url'] = f'https://twitter.com/{user_info["screen_name"]}'

        # attempt to get a more suitable image
        if 'avatar' in profile:
            for rendition in ('_400x400', ''):
                req = requests.head(profile['avatar'].replace('_normal', rendition),
                                    timeout=self._http_timeout)
                if 200 <= req.status_code < 300:
                    LOGGER.info("Found better avatar rendition: %s", req.url)
                    profile['avatar'] = req.url
                    break

        return {k: v for k, v in profile.items() if v}


def from_config(config, storage):
    """ Generate a Twitter handler from the given config dictionary.

    Posible configuration values:

    * ``TWITTER_CLIENT_ID``: The Twitter app's client_id

    * ``TWITTER_CLIENT_SECRET``: The Twitter app's client_secret

    * ``TWITTER_TIMEOUT``: How long to wait for the user to log in

    It is ***HIGHLY RECOMMENDED*** that the client key and secret be provided
    via environment variables or some other mechanism that doesn't involve
    checking these values into source control and exposing them on the
    file system.
    """

    return Twitter(config['TWITTER_CLIENT_ID'],
                   config['TWITTER_CLIENT_SECRET'],
                   config.get('TWITTER_TIMEOUT'),
                   storage)
