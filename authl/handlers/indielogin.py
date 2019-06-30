""" Implementation that uses IndieLogin.com """

import urllib.parse
import uuid
import json
import logging

import requests

from . import Handler
from .. import disposition

LOGGER = logging.getLogger(__name__)


class IndieLogin(Handler):
    def __init__(self, client_id):
        self._client_id = client_id
        self._pending = {}

    def handles_url(self, url):
        return False

    def handles_page(self, headers, content):
        return True

    def initiate_auth(self, id_url, callback_url):
        LOGGER.info("Initiate auth: %s %s", id_url, callback_url)

        state = str(uuid.uuid4())
        self._pending[state] = {
            'id_url': id_url,
            'callback_uri': callback_url,
            # TODO add TTL
        }
        # TODO purge expired ones

        return disposition.Redirect('https://indielogin.com/auth?' +
                                    urllib.parse.urlencode({
                                        'me': id_url,
                                        'client_id': self._client_id,
                                        'redirect_uri': callback_url,
                                        'state': state
                                    }))

    def check_callback(self, url, get, data):
        LOGGER.info("got callback: %s %s", url, get)

        state = get.get('state')
        if not state or state not in self._pending:
            LOGGER.warning("state=%s pending=%s", state, self._pending)
            return disposition.Error("State {state} didn't match".format(state=state))

        if not 'code' in get:
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
