""" Mastodon/Pleroma/Fediverse provider """

import functools
import json
import logging
import re
import urllib.parse
import uuid

import expiringdict
import requests

from .. import disposition
from . import Handler

LOGGER = logging.getLogger(__name__)


class Mastodon(Handler):
    """ Handler for Mastodon and Mastodon-like services """

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

    def __init__(self, name, homepage=None, max_pending=None, pending_ttl=None):
        """ Instantiate a Mastodon handler.

        name -- Human-readable website name
        homepage -- Homepage for the website
        """
        self._name = name
        self._homepage = homepage
        self._pending = expiringdict.ExpiringDict(
            max_len=max_pending or 128,
            max_age_seconds=pending_ttl or 600)

    @staticmethod
    def _get_instance(url):
        match = re.match('@.*@(.*)$', url)
        if match:
            domain = match[1]
        else:
            parsed = urllib.parse.urlparse(url)
            if not parsed.netloc:
                parsed = urllib.parse.urlparse('https://' + url)
            domain = parsed.netloc
        return 'https://' + domain

    def handles_url(self, url):
        # Try to extract out the instance name

        instance = self._get_instance(url)
        if not instance:
            return None

        # we have a domain, does it implement the Mastodon instance API?
        LOGGER.debug("Testing Mastodon instance %s", instance)

        try:
            request = requests.get(instance + '/api/v1/instance')
            if request.status_code != 200:
                LOGGER.debug("Instance endpoint returned error %d", request.status_code)
                return None

            info = json.dumps(request.text)
            for key in ('uri', 'version', 'urls'):
                if key not in info:
                    LOGGER.debug("Instance data missing key '%s'", key)
                    return None

            # This seems to be a Mastodon endpoint; try to figure out the username
            for tmpl in ('@(.*)@', '.*/@(.*)$', '.*/user/(.*)%'):
                match = re.match(tmpl, url)
                if match:
                    return instance + '/@' + match[1]
            return instance
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.debug("Mastodon probe failed: %s", error)

        return False

    def handles_page(self, headers, content, links):
        return False

    @functools.lru_cache(128)
    def _get_client(self, instance, callback):
        """ Get the client data """
        request = requests.post(instance + '/api/v1/apps',
                                data={
                                    'client_name': self._name,
                                    'redirect_uris': callback,
                                    'scopes': 'read:accounts',
                                    'website': self._homepage
                                })
        if request.status_code != 200:
            return None
        return json.loads(request.text)

    def initiate_auth(self, id_url, callback_url):
        instance = self._get_instance(id_url)

        state = str(uuid.uuid4())

        client = self._get_client(instance, callback_url)
        if not client:
            return disposition.Error("Failed to register OAuth client")
        client['instance'] = instance

        self._pending[state] = {**client}

        if client.get('redirect_uri') != callback_url:
            return disposition.Error("Got incorrect callback URL")

        url = instance + '/oauth/authorize?' + urllib.parse.urlencode({
            'client_id': client['client_id'],
            'response_type': 'code',
            'redirect_uri': callback_url,
            'scope': 'read:accounts',
            'state': state
        })
        return disposition.Redirect(url)

    def check_callback(self, url, get, data):
        state = get.get('state')
        if not state:
            return disposition.Error("No transaction ID provided")
        if state not in self._pending:
            LOGGER.warning('state=%s pending=%s', state, self._pending)
            return disposition.Error('Transaction invalid or expired')
        client = self._pending[state]
        instance = client['instance']

        if 'code' not in get:
            return disposition.Error("Missing auth code")

        # Get the actual auth token
        request = requests.post(instance + '/oauth/token',
                                data={
                                    'client_id': client['client_id'],
                                    'client_secret': client['client_secret'],
                                    'grant_type': 'authorization_code',
                                    'code': get['code'],
                                    'redirect_uri': client['redirect_uri']
                                })
        if request.status_code != 200:
            LOGGER.warning('oauth/token: %d %s', request.status_code, request.text)
            return disposition.Error("Could not retrieve access token")

        response = json.loads(request.text)
        if 'access_token' not in response:
            LOGGER.warning("Response did not contain 'access_token': %s", response)
            return disposition.Error("No access token provided")

        token = response['access_token']
        auth_headers = {'Authorization': 'Bearer ' + token}

        def get_credentials():
            # now we can get the authenticated user profile
            request = requests.get(instance + '/api/v1/accounts/verify_credentials',
                                   headers=auth_headers)
            if request.status_code != 200:
                LOGGER.warning('verify_credentials: %d %s', request.status_code, request.text)
                return disposition.Error("Unable to get account credentials")

            response = json.loads(request.text)
            if 'url' not in response:
                LOGGER.warning("Response did not contain 'url': %s", response)
                return disposition.Error("No user URL provided")

            # canonicize the URL and also make sure the domain matches
            id_url = urllib.parse.urljoin(instance, response['url'])
            if urllib.parse.urlparse(id_url).netloc != urllib.parse.urlparse(instance).netloc:
                LOGGER.warning("Instance %s returned response of %s -> %s",
                               instance, response['url'], id_url)
                return disposition.Error("Domains do not match")

            return disposition.Verified(id_url, response)

        result = get_credentials()

        # try to clean up after ourselves
        request = requests.post(instance + '/oauth/revoke', data={
            'client_id': client['client_id'],
            'client_secret': client['client_secret'],
            'token': token
        }, headers=auth_headers)
        if request.status_code != 200:
            LOGGER.warning("Unable to revoke credentials: %d %s", request.status_code, request.text)
        LOGGER.info("Revocation response: %s", request.text)

        return result


def from_config(config):
    """ Generate a Mastodon handler from the given config dictionary.

    Posible configuration values:

    MASTODON_NAME -- the name of your website (required)
    MASTODON_HOMEPAGE -- your website's homepage (recommended)
    """

    return Mastodon(config['MASTODON_NAME'], config.get('MASTODON_HOMEPAGE'))
