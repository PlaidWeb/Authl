""" Mastodon/Pleroma/Fediverse provider """

import functools
import json
import logging
import re
import urllib.parse

import requests

from .. import disposition
from . import oauth

LOGGER = logging.getLogger(__name__)


class Mastodon(oauth.OAuth):
    """ Handler for Mastodon and Mastodon-like services """

    class Client(oauth.Client):
        """ Mastodon OAuth client info """
        # pylint:disable=too-few-public-methods

        def __init__(self, instance, params):
            super().__init__(instance + '/oauth', params)
            self.instance = instance

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
        super().__init__(max_pending, pending_ttl)
        self._name = name
        self._homepage = homepage

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

            info = json.dumps(request.text)
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
    def _get_client(self, id_url, callback_url):
        """ Get the client data """
        instance = self._get_instance(id_url)
        request = requests.post(instance + '/api/v1/apps',
                                data={
                                    'client_name': self._name,
                                    'redirect_uris': callback_url,
                                    'scopes': 'read:accounts',
                                    'website': self._homepage
                                })
        if request.status_code != 200:
            return None
        info = json.loads(request.text)

        if info['redirect_uri'] != callback_url:
            raise ValueError("Got incorrect redirect_uri")

        return Mastodon.Client(instance, {
            **info,
            'scope': 'read:accounts'
        })

    def _get_identity(self, client, auth_headers):
        request = requests.get(
            client.instance + '/api/v1/accounts/verify_credentials',
            headers=auth_headers)
        if request.status_code != 200:
            LOGGER.warning('verify_credentials: %d %s', request.status_code, request.text)
            return disposition.Error("Unable to get account credentials")

        response = json.loads(request.text)
        if 'url' not in response:
            LOGGER.warning("Response did not contain 'url': %s", response)
            return disposition.Error("No user URL provided")

        # canonicize the URL and also make sure the domain matches
        id_url = urllib.parse.urljoin(client.instance, response['url'])
        if urllib.parse.urlparse(id_url).netloc != urllib.parse.urlparse(client.instance).netloc:
            LOGGER.warning("Instance %s returned response of %s -> %s",
                           client.instance, response['url'], id_url)
            return disposition.Error("Domains do not match")

        return disposition.Verified(id_url, response)


def from_config(config):
    """ Generate a Mastodon handler from the given config dictionary.

    Posible configuration values:

    MASTODON_NAME -- the name of your website (required)
    MASTODON_HOMEPAGE -- your website's homepage (recommended)
    """

    return Mastodon(config['MASTODON_NAME'], config.get('MASTODON_HOMEPAGE'))
