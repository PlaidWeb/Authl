"""
Fediverse handler
=================

This handler allows login via Fediverse instances; currently `Mastodon
<https://joinmastodon.org>`_ and `Pleroma <https://pleroma.social>`_ are
supported, as is anything else with basic support for the Mastodon client API.

See :py:func:`authl.from_config` for the simplest configuration mechanism.

This handler registers itself with a ``cb_id`` of ``"fv"``.

"""

import logging
import re
import time
import typing
import urllib.parse

import mastodon
import requests

from .. import disposition, tokens, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


class Fediverse(Handler):
    """ Handler for Fediverse services (Mastodon, Pleroma) """

    @property
    def service_name(self):
        return "Fediverse"

    @property
    def url_schemes(self):
        return [('https://%', 'instance/')]

    @property
    def description(self):
        return """Identifies you using your choice of Fediverse instance
        (currently supported: <a href="https://joinmastodon.org/">Mastodon</a>,
        <a href="https://pleroma.social/">Pleroma</a>)"""

    @property
    def cb_id(self):
        return 'fv'

    @property
    def logo_html(self):
        return [(utils.read_icon('mastodon.svg'), 'Mastodon'),
                (utils.read_icon('pleroma.svg'), 'Pleroma')]

    def __init__(self, name: str,
                 token_store: tokens.TokenStore,
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
        self._http_timeout = 30

    @staticmethod
    def _get_instance(url, timeout: int) -> typing.Optional[str]:
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc:
            parsed = urllib.parse.urlparse('https://' + url)
        domain = parsed.netloc

        instance = 'https://' + domain

        try:
            LOGGER.debug("Trying Fediverse instance: %s", instance)
            request = requests.get(instance + '/api/v1/instance', timeout=timeout)
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
        """
            Checks for an ``/api/v1/instance`` endpoint to determine if this
            is a Mastodon-compatible instance
        """
        LOGGER.info("Checking URL %s", url)

        instance = self._get_instance(url, self._http_timeout)
        if not instance:
            LOGGER.debug("Not a Fediverse instance: %s", url)
            return None

        # This seems to be a Fediverse endpoint; try to figure out the username
        for tmpl in ('.*/@(.*)$', '.*/user/(.*)$'):
            match = re.match(tmpl, url)
            if match:
                LOGGER.debug("handles_url: instance %s user %s", instance, match[1])
                return instance + '/@' + match[1]

        return instance

    @staticmethod
    def _get_identity(instance, response, redir) -> disposition.Disposition:
        try:
            # canonicize the URL and also make sure the domain matches
            id_url = urllib.parse.urljoin(instance, response['url'])
            if urllib.parse.urlparse(id_url).netloc != urllib.parse.urlparse(instance).netloc:
                LOGGER.warning("Instance %s returned response of %s -> %s",
                               instance, response['url'], id_url)
                return disposition.Error("Domains do not match", redir)

            profile = {
                'name': response.get('display_name'),
                'bio': response.get('source', {}).get('note'),
                'avatar': response.get('avatar_static', response.get('avatar'))
            }

            # Attempt to parse useful stuff out of the fields source
            for field in response.get('source', {}).get('fields', []):
                name = field.get('name', '')
                value = field.get('value', '')
                if 'homepage' not in profile and urllib.parse.urlparse(value).scheme:
                    profile['homepage'] = value
                elif 'pronoun' in name.lower():
                    profile['pronouns'] = value

            return disposition.Verified(id_url, redir, {k: v for k, v in profile.items() if v})
        except KeyError:
            return disposition.Error('Missing user profile', redir)
        except (TypeError, AttributeError):
            return disposition.Error('Malformed user profile', redir)

    def initiate_auth(self, id_url, callback_uri, redir):
        try:
            instance = self._get_instance(id_url, self._http_timeout)
            client_id, client_secret = mastodon.Mastodon.create_app(
                api_base_url=instance,
                client_name=self._name,
                website=self._homepage,
                scopes=['read:accounts'],
                redirect_uris=callback_uri,
            )
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error(f"Failed to register client: {err}", redir)

        client = mastodon.Mastodon(
            api_base_url=instance,
            client_id=client_id,
            client_secret=client_secret
        )

        state = self._token_store.put((
            instance,
            client_id,
            client_secret,
            time.time(),
            redir
        ))

        url = client.auth_request_url(
            redirect_uris=callback_uri,
            scopes=['read:accounts'],
            state=state
        )

        return disposition.Redirect(url)

    def check_callback(self, url, get, data):
        print(url, get)
        try:
            (
                instance,
                client_id,
                client_secret,
                when,
                redir
            ) = self._token_store.pop(get['state'])
        except (KeyError, ValueError):
            return disposition.Error("Invalid transaction", '')

        if 'error' in get:
            return disposition.Error("Error signing into instance: "
                                     + get.get('error_description', get['error']),
                                     redir)

        if time.time() > when + self._timeout:
            return disposition.Error("Login timed out", redir)

        client = mastodon.Mastodon(
            api_base_url=instance,
            client_id=client_id,
            client_secret=client_secret
        )

        try:
            client.log_in(
                code=get['code'],
                redirect_uri=url,
                scopes=['read:accounts'],
            )
        except KeyError as err:
            return disposition.Error(f"Missing {err}", redir)
        except Exception as err:  # pylint:disable=broad-except
            return disposition.Error(f"Error signing into instance: {err}", redir)

        result = self._get_identity(instance, client.me(), redir)

        # clean up after ourselves
        client.revoke_access_token()

        return result


def from_config(config, token_store: tokens.TokenStore):
    """ Generate a Fediverse handler from the given config dictionary.

    :param dict config: Configuration values; relevant keys:

        * ``FEDIVERSE_NAME``: the name of your website (required)

        * ``FEDIVERSE_HOMEPAGE``: your website's homepage (recommended)

        * ``FEDIVERSE_TIMEOUT``: the maximum time to wait for login to complete

    :param tokens.TokenStore token_store: The authentication token storage
    """

    return Fediverse(config.get('FEDIVERSE_NAME'), token_store,
                     timeout=config.get('FEDIVERSE_TIMEOUT'),
                     homepage=config.get('FEDIVERSE_HOMEPAGE'))
