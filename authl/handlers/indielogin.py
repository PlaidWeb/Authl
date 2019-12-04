""" Implementation that uses IndieLogin.com """

import logging
import urllib.parse

import requests

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class IndieLogin(Handler):
    """ A hdndler that makes use of indielogin.com as an authentication broker.
    This allows anyone with an IndieAuth endpoint or a rel="me" attribute that
    points to a supported third-party authentication mechanism (e.g. GitHub or
    email). See https://indielogin.com for more information.
    """

    @property
    def service_name(self):
        return 'IndieLogin'

    @property
    def url_schemes(self):
        return [('%', 'https://domain.example.com')]

    @property
    def description(self):
        return """Uses a third-party <a href="https://indielogin.com/">IndieLogin</a>
        endpoint to securely log you in based on your personal profile page."""

    @property
    def cb_id(self):
        return 'il'

    def __init__(self, client_id: str,
                 token_store: dict,
                 timeout: int = None,
                 endpoint: str = None):
        """ Construct an IndieLogin handler, to work with indielogin.com. See
        https://indielogin.com/api for more information.

        :param str client_id: the indielogin.com client id
        :param token_store: Login token generator
        :param int timeout: How long to wait for a login to complete (default: 600)
        :param str endpoint: Which IndieLogin instance to authenticate against
        """

        self._client_id = client_id
        self._token_store = token_store
        self._endpoint = endpoint or 'https://indielogin.com/auth'
        self._timeout = timeout or 600

    def handles_page(self, url, headers, content, links):
        # Check to see if there's any appropriate links
        if links.get('authorization_endpoint'):
            return True

        if content.find_all(['a', 'link'], rel=['me', 'authorization_endpoint']):
            return True

        return False

    def initiate_auth(self, id_url, callback_uri, redir):
        LOGGER.info('Initiate auth: %s %s', id_url, callback_uri)

        # register a new transaction ID
        state = self._token_store.dumps((callback_uri, redir))

        auth_url = (
            self._endpoint
            + '?'
            + urllib.parse.urlencode(
                {
                    'me': id_url,
                    'client_id': utils.resolve_value(self._client_id),
                    'redirect_uri': callback_uri,
                    'state': state,
                }
            )
        )
        return disposition.Redirect(auth_url)

    def check_callback(self, url, get, data):
        LOGGER.info('got callback: %s %s', url, get)

        state = get.get('state')
        if not state:
            return disposition.Error('No transaction ID provided', None)

        try:
            callback_uri, redir = utils.unpack_token(self._token_store, state, self._timeout)
        except disposition.Disposition as disp:
            return disp

        if 'code' not in get:
            return disposition.Error('Missing auth code', redir)

        req = requests.post(
            self._endpoint,
            {
                'code': get['code'],
                'redirect_uri': callback_uri,
                'client_id': utils.resolve_value(self._client_id),
            },
        )

        try:
            result = req.json()
        except ValueError:
            return disposition.Error("Got invalid response JSON", redir)

        if req.status_code != 200:
            return disposition.Error(
                'Got error {code}: {text}'.format(
                    code=req.status_code, text=result.get('error_description')
                ), redir
            )

        return disposition.Verified(result.get('me'), redir)


def from_config(config, token_store):
    """ Instantiate an IndieLogin handler from a configuration dictionary.

    Possible configuration values:

    INDIELOGIN_CLIENT_ID -- the client ID to send to the IndieLogin service (required)
    INDIELOGIN_ENDPOINT -- the endpoint to use for the IndieLogin service
        (default: https://indielogin.com/auth)
    INDIELOGIN_OPEN_TTL -- the time-to-live of an open request, in seconds
    """

    return IndieLogin(
        config['INDIELOGIN_CLIENT_ID'],
        token_store,
        timeout=config.get('INDIELOGIN_OPEN_TTL'),
        endpoint=config.get('INDIELOGIN_ENDPOINT'),
    )
