""" Implementation that uses IndieLogin.com """

import urllib.parse
import uuid
import json
import logging

import requests
import expiringdict

from . import Handler
from .. import disposition

LOGGER = logging.getLogger(__name__)


class IndieLogin(Handler):
    """ A hdndler that makes use of indielogin.com as an authentication broker.
    This allows anyone with an IndieAuth endpoint or a rel="me" attribute that
    points to a supported third-party authentication mechanism (e.g. GitHub or
    email). See https://indielogin.com for more information.
    """

    def __init__(self, client_id, max_pending=128, pending_ttl=600,
                 instance='https://indielogin.com'):
        """ Construct an IndieLogin handler, to work with indielogin.com. See
        https://indielogin.com/api for more information.

        client_id -- the indielogin.com client id
        max_pending -- the maximum number of pending login requests
        pending_ttl -- how long the user has to complete login, in seconds
        instance -- which IndieLogin instance to authenticate against
        """

        self._client_id = client_id
        self._pending = expiringdict.ExpiringDict(max_len=max_pending, max_age_seconds=pending_ttl)
        self._base_url = instance

    def handles_url(self, url):
        return False

    def handles_page(self, headers, content):
        return True

    def initiate_auth(self, id_url, callback_url):
        LOGGER.info("Initiate auth: %s %s", id_url, callback_url)

        # register a new CSRF token
        state = str(uuid.uuid4())
        self._pending[state] = {
            'id_url': id_url,
            'callback_uri': callback_url,
        }

        auth_url = urllib.parse.urljoin(
            self._base_url, 'auth?' +
            urllib.parse.urlencode({
                'me': id_url,
                'client_id': self._client_id,
                'redirect_uri': callback_url,
                'state': state
            }))
        return disposition.Redirect(auth_url)

    def check_callback(self, url, get, data):
        LOGGER.info("got callback: %s %s", url, get)

        state = get.get('state')
        if not state:
            return disposition.Error("No CSRF token specified")
        if not state or state not in self._pending:
            LOGGER.warning("state=%s pending=%s", state, self._pending)
            return disposition.Error("CSRF token invalid or expired")

        if 'code' not in get:
            return disposition.Error("Missing auth code")

        item = self._pending[state]
        del self._pending[state]
        req = requests.post('https://indielogin.com/auth', {
            'code': get['code'],
            'redirect_uri': item['callback_uri'],
            'client_id': self._client_id
        })

        result = json.loads(req.text)

        if req.status_code != 200:
            return disposition.Error("Got error {code}: {text}".format(
                code=req.status_code, text=result.get('error_description')))

        return disposition.Verified(result.get('me'))

    def service_name(self):
        return "Loopback"

    def url_scheme(self):
        return 'test:%', 'example'
