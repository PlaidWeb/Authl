""" Fediverse/Pleroma/Fediverse provider """

import functools
import logging
import re
import typing
import urllib.parse

import requests

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class Fediverse(Handler):
    """ Handler for Fediverse services (Mastodon, Pleroma) """

    class Client:
        """ Fediverse OAuth client info """
        # pylint:disable=too-few-public-methods

        def __init__(self, instance, params, secrets):
            self.instance = instance
            self.auth_endpoint = instance + '/oauth/authorize'
            self.token_endpoint = instance + '/oauth/token'
            self.revoke_endpoint = instance + '/oauth/revoke'
            self.params = params
            self.secrets = secrets

        def to_tuple(self):
            """ Convert this to a JSON-serializable tuple """
            return self.instance, self.params, self.secrets

    @property
    def service_name(self):
        return "Fediverse"

    @property
    def url_schemes(self):
        return [('https://%', 'instance/@username'),
                ('@%', 'username@instance')]

    @property
    def description(self):
        return """Identifies you using your choice of Fediverse instance
        (currently supported: <a href="https://joinmastodon.org/">Mastodon</a>,
        <a href="https://pleroma.social/">Pleroma</a>)"""

    @property
    def cb_id(self):
        return 'md'

    def __init__(self, name: str,
                 token_store: typing.Dict[str, typing.Any],
                 timeout: typing.Optional[int] = None,
                 homepage: typing.Optional[str] = None):
        """ Instantiate a Fediverse handler.

        :param str name: Human-readable website name
        :param str homepage: Homepage for the website
        :param token_store: Storage for session tokens
        :param int timeout: How long to allow a user to wait to log in, in seconds

        """
        self._name = name
        self._homepage = homepage
        self._token_store = token_store
        self._timeout = timeout or 600

    @staticmethod
    @functools.lru_cache(128)
    def _get_instance(url) -> typing.Optional[str]:
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
            LOGGER.debug("Trying Fediverse instance: %s", instance)
            request = requests.get(instance + '/api/v1/instance')
            if request.status_code != 200:
                LOGGER.debug("Instance endpoint returned error %d", request.status_code)
                return None

            info = request.json()
            for key in ('uri', 'version', 'urls'):
                if key not in info:
                    LOGGER.debug("Instance data missing key '%s'", key)
                    return None

            LOGGER.info("Found Fediverse instance: %s", instance)
            return instance
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.debug("Fediverse probe failed: %s", error)

        return None

    def handles_url(self, url):
        LOGGER.info("Checking URL %s", url)

        instance = self._get_instance(url)
        if not instance:
            LOGGER.debug("Not a Fediverse instance: %s", url)
            return None

        # This seems to be a Fediverse endpoint; try to figure out the username
        for tmpl in ('@(.*)@', '.*/@(.*)$', '.*/user/(.*)%'):
            match = re.match(tmpl, url)
            if match:
                LOGGER.debug("handles_url: instance %s user %s", instance, match[1])
                return instance + '/@' + match[1]

        return instance

    @functools.lru_cache(128)
    def _get_client(self, id_url: str, callback_uri: str) -> typing.Optional['Fediverse.Client']:
        """ Get the client data """
        instance = self._get_instance(id_url)
        if not instance:
            return None
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

        return Fediverse.Client(instance, {
            'client_id': info['client_id'],
            'redirect_uri': info['redirect_uri'],
            'scope': 'read:accounts'
        }, {
            'client_secret': info['client_secret']
        })

    @staticmethod
    def _get_identity(client, auth_headers, redir) -> disposition.Disposition:
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
        try:
            client = self._get_client(id_url, callback_uri)
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error("Failed to register OAuth client: " + str(err), redir)

        if not client:
            return disposition.Error("Failed to register OAuth client", redir)

        state = self._token_store.dumps((client.to_tuple(), redir))

        url = client.auth_endpoint + '?' + urllib.parse.urlencode(
            {**client.params,
             'state': state,
             'response_type': 'code'})

        return disposition.Redirect(url)

    def check_callback(self, url, get, data):
        state = get.get('state')
        if not state:
            return disposition.Error("No transaction ID provided", None)

        try:
            client_tuple, redir = utils.unpack_token(self._token_store, state, self._timeout)
        except disposition.Disposition as disp:
            return disp
        client = Fediverse.Client(*client_tuple)

        if 'error' in get:
            return disposition.Error("Error signing into Fediverse", redir)

        try:
            request = requests.post(client.token_endpoint,
                                    {**client.params,
                                     **client.secrets,
                                     'grant_type': 'authorization_code',
                                     'code': get['code']})
            if request.status_code != 200:
                LOGGER.warning('oauth/token: %d %s', request.status_code, request.text)
                return disposition.Error("Could not retrieve access token", redir)

            response = request.json()
            token = response['access_token']
            auth_headers = {'Authorization': 'Bearer ' + token}

            result = self._get_identity(client, auth_headers, redir)
        except KeyError as key:
            result = disposition.Error("Missing " + str(key), redir)

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
    """ Generate a Fediverse handler from the given config dictionary.

    Posible configuration values:

    Fediverse_NAME -- the name of your website (required)
    Fediverse_HOMEPAGE -- your website's homepage (recommended)
    Fediverse_TIMEOUT -- the maximum time to wait for login to complete
    """

    def get_cfg(key: str, dfl=None):
        for pfx in ('FEDIVERSE_', 'MASTODON_'):
            if pfx + key in config:
                if pfx != 'FEDIVERSE_':
                    LOGGER.warning("Configuration key %s has changed to %s",
                                   pfx + key, 'FEDIVERSE_' + key)
                return config[pfx + key]
        return dfl

    return Fediverse(get_cfg('NAME'), token_store,
                     timeout=get_cfg('TIMEOUT'),
                     homepage=get_cfg('HOMEPAGE'))
