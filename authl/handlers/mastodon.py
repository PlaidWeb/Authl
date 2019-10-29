""" Mastodon/Pleroma/Fediverse provider """

import functools
import logging
import re
import urllib.parse

import requests

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class Mastodon(Handler):
    """ Handler for Mastodon and Mastodon-like services """

    class Client:
        """ Mastodon OAuth client info """
        # pylint:disable=too-few-public-methods

        def __init__(self, instance, params, secrets):
            self.instance = instance
            self.auth_endpoint = instance + '/oauth/authorize'
            self.token_endpoint = instance + '/oauth/token'
            self.revoke_endpoint = instance + '/oauth/revoke'
            self.params = params
            self.secrets = secrets

    @property
    def service_name(self):
        return "Mastodon"

    @property
    def url_schemes(self):
        return [('https://%', 'instance/@username'),
                ('@%', 'username@instance')]

    @property
    def description(self):
        return """Identifies you using your choice of
        <a href="https://joinmastodon.org/">Mastodon</a>
        instance."""

    @property
    def cb_id(self):
        return 'md'

    def __init__(self, name: str, token_store: dict, homepage: str = None):
        """ Instantiate a Mastodon handler.

        :param str name: Human-readable website name

        :param token_store: Storage for session tokens

        :paramm str homepage: Homepage for the website
        """
        self._name = name
        self._homepage = homepage
        self._pending = token_store

    @staticmethod
    @functools.lru_cache(128)
    def _get_instance(url):
        match = re.match('@.*@(.*)$', url)
        if match:
            domain = match[1]
        else:
            parsed = urllib.parse.urlparse(url)
            if not parsed.netloc:
                parsed = urllib.parse.urlparse('https://' + url)
            domain = parsed.netloc

        instance = 'https://' + domain

        try:
            LOGGER.debug("Trying Mastodon instance: %s", instance)
            request = requests.get(instance + '/api/v1/instance')
            if request.status_code != 200:
                LOGGER.debug("Instance endpoint returned error %d", request.status_code)
                return None

            info = request.json()
            for key in ('uri', 'version', 'urls'):
                if key not in info:
                    LOGGER.debug("Instance data missing key '%s'", key)
                    return None

            LOGGER.info("Found Mastodon instance: %s", instance)
            return instance
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.debug("Mastodon probe failed: %s", error)

        return None

    def handles_url(self, url):
        LOGGER.info("Checking URL %s", url)

        instance = self._get_instance(url)
        if not instance:
            LOGGER.debug("Not a Mastodon instance: %s", url)
            return None

        # This seems to be a Mastodon endpoint; try to figure out the username
        for tmpl in ('@(.*)@', '.*/@(.*)$', '.*/user/(.*)%'):
            match = re.match(tmpl, url)
            if match:
                LOGGER.debug("handles_url: instance %s user %s", instance, match[1])
                return instance + '/@' + match[1]

        return instance

    @functools.lru_cache(128)
    def _get_client(self, id_url, callback_uri):
        """ Get the client data """
        instance = self._get_instance(id_url)
        request = requests.post(instance + '/api/v1/apps',
                                data={
                                    'client_name': self._name,
                                    'redirect_uris': callback_uri,
                                    'scopes': 'read:accounts',
                                    'website': self._homepage
                                })
        if request.status_code != 200:
            return None
        info = request.json()

        if info['redirect_uri'] != callback_uri:
            raise ValueError("Got incorrect redirect_uri")

        return Mastodon.Client(instance, {
            'client_id': info['client_id'],
            'redirect_uri': info['redirect_uri'],
            'scope': 'read:accounts'
        }, {
            'client_secret': info['client_secret']
        })

    @staticmethod
    def _get_identity(client, auth_headers, redir):
        request = requests.get(
            client.instance + '/api/v1/accounts/verify_credentials',
            headers=auth_headers)
        if request.status_code != 200:
            LOGGER.warning('verify_credentials: %d %s', request.status_code, request.text)
            return disposition.Error("Unable to get account credentials", redir)

        response = request.json()
        if 'url' not in response:
            LOGGER.warning("Response did not contain 'url': %s", response)
            return disposition.Error("No user URL provided", redir)

        # canonicize the URL and also make sure the domain matches
        id_url = urllib.parse.urljoin(client.instance, response['url'])
        if urllib.parse.urlparse(id_url).netloc != urllib.parse.urlparse(client.instance).netloc:
            LOGGER.warning("Instance %s returned response of %s -> %s",
                           client.instance, response['url'], id_url)
            return disposition.Error("Domains do not match", redir)

        return disposition.Verified(id_url, redir, response)

    def initiate_auth(self, id_url, callback_uri, redir):
        state = utils.gen_token()
        try:
            client = self._get_client(id_url, callback_uri)
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error("Failed to register OAuth client: " + str(err), redir)

        if not client:
            return disposition.Error("Failed to register OAuth client", redir)

        self._pending[state] = (client, redir)

        url = client.auth_endpoint + '?' + urllib.parse.urlencode(
            {**client.params,
             'state': state,
             'response_type': 'code'})

        return disposition.Redirect(url)

    def check_callback(self, url, get, data):
        # pylint:disable=too-many-return-statements
        if 'error' in get:
            return disposition.Error(get.get('error_description'), 'Error signing into Mastodon')

        state = get.get('state')
        if not state:
            return disposition.Error("No transaction ID provided", None)
        if state not in self._pending:
            return disposition.Error('Transaction invalid or expired', None)
        client, redir = self._pending[state]

        if 'code' not in get:
            return disposition.Error("Missing auth code", redir)

        request = requests.post(client.token_endpoint,
                                {**client.params,
                                 **client.secrets,
                                 'grant_type': 'authorization_code',
                                 'code': get['code']})
        if request.status_code != 200:
            LOGGER.warning('oauth/token: %d %s', request.status_code, request.text)
            return disposition.Error("Could not retrieve access token", redir)

        response = request.json()
        if 'access_token' not in response:
            LOGGER.warning("Response did not contain 'access_token': %s", response)
            return disposition.Error("No access token provided", redir)

        token = response['access_token']
        auth_headers = {'Authorization': 'Bearer ' + token}

        result = self._get_identity(client, auth_headers, redir)

        # try to clean up after ourselves
        request = requests.post(client.revoke_endpoint, data={
            **client.params,
            **client.secrets,
            'token': token
        }, headers=auth_headers)
        if request.status_code != 200:
            LOGGER.warning("Unable to revoke OAuth token: %d %s",
                           request.status_code,
                           request.text)
        LOGGER.info("Revocation response: %s", request.text)

        return result


def from_config(config, token_store):
    """ Generate a Mastodon handler from the given config dictionary.

    Posible configuration values:

    MASTODON_NAME -- the name of your website (required)
    MASTODON_HOMEPAGE -- your website's homepage (recommended)
    """

    return Mastodon(config['MASTODON_NAME'], token_store, config.get('MASTODON_HOMEPAGE'))
