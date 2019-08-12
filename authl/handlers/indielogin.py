""" Implementation that uses IndieLogin.com """

import json
import logging
import urllib.parse

import expiringdict
import requests

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class IndieLogin(Handler):
    """ A hdndler that makes use of indielogin.com as an authentication broker.
    This allows anyone with an IndieAuth endpoint or a rel="me" attribute that
    points to a supported third-party authentication mechanism (e.g. GitHub or
    email). See https://indielogin.com for more information.

    Arguments:

    client_id -- the client ID to send to the IndieLogin endpoint; can be a callable
    max_pending -- the maximum number of pending connections to keep open (default: 128)
    pending_ttl -- how long to wait for a pending connection, in seconds (default: 600)
    endpoint -- the IndieLogin endpoint to authenticate against
    """

    @property
    def service_name(self):
        return 'IndieLogin'

    @property
    def url_schemes(self):
        return [('%', 'https://website.name')]

    @property
    def description(self):
        return """Uses a third-party <a href="https://indielogin.com/">IndieLogin</a>
        endpoint to securely log you in based on your personal profile page."""

    def __init__(self, client_id, max_pending=None, pending_ttl=None, endpoint=None):
        """ Construct an IndieLogin handler, to work with indielogin.com. See
        https://indielogin.com/api for more information.

        client_id -- the indielogin.com client id
        max_pending -- the maximum number of pending login requests
        pending_ttl -- how long the user has to complete login, in seconds
        instance -- which IndieLogin instance to authenticate against
        """

        self._client_id = client_id
        self._pending = expiringdict.ExpiringDict(
            max_len=max_pending or 128, max_age_seconds=pending_ttl or 600
        )
        self._endpoint = endpoint or 'https://indielogin.com/auth'

    def handles_page(self, url, headers, content, links):
        # Check to see if there's any appropriate links
        if links.get('authorization_endpoint'):
            return True

        if content.find_all(['a', 'link'], rel=['me', 'authorization_endpoint']):
            return True

        return False

    def initiate_auth(self, id_url, callback_url):
        LOGGER.info('Initiate auth: %s %s', id_url, callback_url)

        # register a new transaction ID
        state = utils.gen_token()
        self._pending[state] = {'id_url': id_url, 'callback_uri': callback_url}

        auth_url = (
            self._endpoint
            + '?'
            + urllib.parse.urlencode(
                {
                    'me': id_url,
                    'client_id': utils.resolve_value(self._client_id),
                    'redirect_uri': callback_url,
                    'state': state,
                }
            )
        )
        return disposition.Redirect(auth_url)

    def check_callback(self, url, get, data):
        LOGGER.info('got callback: %s %s', url, get)

        state = get.get('state')
        if not state:
            return disposition.Error('No transaction ID provided')
        if state not in self._pending:
            LOGGER.warning('state=%s pending=%s', state, self._pending)
            return disposition.Error('Transaction invalid or expired')

        if 'code' not in get:
            return disposition.Error('Missing auth code')

        item = self._pending[state]
        del self._pending[state]
        req = requests.post(
            self._endpoint,
            {
                'code': get['code'],
                'redirect_uri': item['callback_uri'],
                'client_id': utils.resolve_value(self._client_id),
            },
        )

        result = json.loads(req.text)

        if req.status_code != 200:
            return disposition.Error(
                'Got error {code}: {text}'.format(
                    code=req.status_code, text=result.get('error_description')
                )
            )

        return disposition.Verified(result.get('me'))


def from_config(config):
    """ Instantiate an IndieLogin handler from a configuration dictionary.

    Possible configuration values:

    INDIELOGIN_CLIENT_ID -- the client ID to send to the IndieLOgin service (required)
    INDIELOGIN_ENDPOINT -- the endpoint to use for the IndieLogin service
        (default: https://indielogin.com/auth)
    INDIELOGIN_OPEN_MAX -- the maximum number of open requests to track
    INDIELOGIN_OPEN_TTL -- the time-to-live of an open request, in seconds
    """

    return IndieLogin(
        config['INDIELOGIN_CLIENT_ID'],
        max_pending=config.get('INDIELOGIN_OPEN_MAX'),
        pending_ttl=config.get('INDIELOGIN_OPEN_TTL'),
        endpoint=config.get('INDIELOGIN_ENDPOINT'),
    )
