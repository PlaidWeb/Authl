""" OAuth handler base """

import json
import logging
import typing
import urllib.parse
from abc import abstractmethod

import expiringdict
import requests

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class Client:
    """ Base class for an OAuth client. Has at least the following properties:

    :param str oauth_endpoint: Base endpoint for OAuth methods, e.g.
        https://example.com/oauth

    :param auth_params: Parameters to pass along to the OAuth endpoint
    """
    # pylint:disable=too-few-public-methods

    def __init__(self, oauth_endpoint: str, params: typing.Dict[str, str]):
        # pylint:disable=too-many-arguments
        self.oauth_endpoint = oauth_endpoint
        self.params = params


class OAuth(Handler):
    """ Abstract intermediate class for OAuth-based protocols """

    @abstractmethod
    def _get_client(self, id_url: str, callback_url: str) -> Client:
        """ Get the ClientInfo for the specified identity URL and callback URL """

    @abstractmethod
    def _get_identity(self,
                      client: Client,
                      auth_headers: typing.Dict[str, str]
                      ) -> disposition.Disposition:
        """ Given an OAuth client and token, get the identity check """

    def __init__(self, max_pending, pending_ttl):
        self._pending = expiringdict.ExpiringDict(
            max_len=max_pending or 128,
            max_age_seconds=pending_ttl or 600)

    def initiate_auth(self, id_url, callback_url):
        state = utils.gen_token()
        client = self._get_client(id_url, callback_url)
        if not client:
            return disposition.Error("Failed to register OAuth client")

        self._pending[state] = client

        url = client.oauth_endpoint + '/authorize?' + urllib.parse.urlencode(
            {**client.params,
             'state': state,
             'response_type': 'code'})

        return disposition.Redirect(url)

    def check_callback(self, url, get, data):
        state = get.get('state')
        if not state:
            return disposition.Error("No transaction ID provided")
        if state not in self._pending:
            return disposition.Error('Transaction invalid or expired')
        client = self._pending[state]

        if 'code' not in get:
            return disposition.Error("Missing auth code")

        # Get the actual auth token
        request = requests.post(client.oauth_endpoint + '/token',
                                {**client.params,
                                 'grant_type': 'authorization_code',
                                 'code': get['code']})
        if request.status_code != 200:
            LOGGER.warning('oauth/token: %d %s', request.status_code, request.text)
            return disposition.Error("Could not retrieve access token")

        response = json.loads(request.text)
        if 'access_token' not in response:
            LOGGER.warning("Response did not contain 'access_token': %s", response)
            return disposition.Error("No access token provided")

        token = response['access_token']
        auth_headers = {'Authorization': 'Bearer ' + token}

        result = self._get_identity(client, auth_headers)

        # try to clean up after ourselves
        request = requests.post(client.oauth_endpoint + '/revoke', data={
            **client.params,
            'token': token
        }, headers=auth_headers)
        if request.status_code != 200:
            LOGGER.warning("Unable to revoke OAuth token: %d %s",
                           request.status_code,
                           request.text)
        LOGGER.info("Revocation response: %s", request.text)

        return result
