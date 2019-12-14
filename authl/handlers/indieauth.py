""" IndieAuth login handler. """

import logging
import typing
import urllib.parse

import requests
from bs4 import BeautifulSoup

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)


def find_endpoint(id_url: str = None,
                  links: typing.Dict = None,
                  content: BeautifulSoup = None) -> typing.Optional[str]:
    """ Given an identity URL, discover its IndieAuth endpoint

    :param str id_url: an identity URL to check
    :param links: a request.links object from a requests operation
    :param BeautifulSoup content: a BeautifulSoup parse tree of an HTML document
    """
    def _link_endpoint(links):
        if not links:
            return None

        LOGGER.debug("checking indieauth by link header")
        if 'authorization_endpoint' in links:
            return links['authorization_endpoint']['url']
        return None

    def _content_endpoint(content):
        if not content:
            return None

        LOGGER.debug("checking indieauth by link tag")
        link = content.find('link', rel='authorization_endpoint')
        if link:
            return link.get('href')
        return None

    request = utils.request_url(id_url) if id_url and not links or not content else None
    if request:
        links = request.links
        content = BeautifulSoup(request.text, 'html.parser')
    return _link_endpoint(links) or _content_endpoint(content)


def verify_id(request_id: str, response_id: str) -> typing.Optional[str]:
    """ Given an ID from an identity request and its verification response,
    ensure that the verification response is a valid URL for the request.

    Returns a normalized version of the response ID, or None if the URL could
    not be verified.
    """

    orig = urllib.parse.urlparse(request_id)
    resp = urllib.parse.urlparse(response_id)
    LOGGER.debug('orig=%s resp=%s', orig, resp)

    # host must match
    if orig.netloc != resp.netloc:
        LOGGER.debug("netloc mismatch %s %s", orig.netloc, resp.netloc)
        return None

    # path must be more specific; provisional, see
    # https://github.com/indieweb/indieauth/issues/35
    orig_path = orig.path.split('/')
    resp_path = resp.path.split('/')

    # Remove trailing empty path components from the original path
    if not orig_path[-1]:
        orig_path.pop()

    LOGGER.debug("orig_path: %s", orig_path)
    LOGGER.debug("resp_path: %s", resp_path)

    # normalize the response path
    norm_path = ['']
    for part in resp_path:
        if part == '..':
            norm_path.pop()
            if not norm_path:
                LOGGER.debug("path attempted escape")
                return None
        elif part not in ('', '.'):
            norm_path.append(part)
    # allow a trailing slash
    if resp_path[-1] == '':
        norm_path.append('')

    LOGGER.debug("norm_path: %s", norm_path)

    if norm_path[:len(orig_path)] != orig_path:
        LOGGER.debug("path mismatch")
        return None

    # construct the resulting URL
    valid = urllib.parse.urlunparse(resp._replace(path='/'.join(norm_path)))
    LOGGER.debug("valid URL: %s", valid)
    return valid


class IndieAuth(Handler):
    """ Directly support login via IndieAuth, without requiring third-party
    IndieLogin brokerage.

    IndieAuth is just barely different enough from baseline OAuth that it's
    easier to just reimplement it directly, rather than trying to use the OAuth
    base class.
    """

    @property
    def service_name(self):
        return 'IndieAuth'

    @property
    def url_schemes(self):
        # pylint:disable=duplicate-code
        return [('%', 'https://domain.example.com')]

    @property
    def description(self):
        return """Supports login via an
        <a href="https://indieweb.org/IndieAuth">IndieAuth</a> provider. """

    @property
    def cb_id(self):
        return 'ia'

    def __init__(self, client_id, token_store, timeout: int = None):
        """ Construct an IndieAuth handler

        :param client_id: The client_id to send to the remote IndieAuth
        provider. Can be a string or a function (e.g. lambda:flask.request.url_root)

        :param token_store: Storage for the tokens

        :param int timeout: Maximum time to wait for login to complete (default: 600)
        """

        self._client_id = client_id
        self._token_store = token_store
        self._timeout = timeout or 600

        self._endpoints = utils.LRUDict()

    def handles_page(self, url, headers, content, links):
        """ If we have the appropriate link rels, register the endpoint now """
        endpoint = find_endpoint(links=links, content=content)

        if endpoint:
            # cache this for later so we don't have to look it up again
            LOGGER.info("%s: has IndieAuth endpoint %s", url, endpoint)
            self._endpoints[url] = endpoint

        return endpoint

    def _get_endpoint(self, id_url):
        if id_url in self._endpoints:
            return self._endpoints[id_url]

        endpoint = find_endpoint(id_url)
        if endpoint:
            self._endpoints[id_url] = endpoint

        return endpoint

    def initiate_auth(self, id_url, callback_uri, redir):
        endpoint = self._get_endpoint(id_url)
        if not endpoint:
            return disposition.Error("Failed to get IndieAuth endpoint", redir)

        state = self._token_store.dumps(((id_url, endpoint, callback_uri), redir))

        client_id = utils.resolve_value(self._client_id)
        LOGGER.debug("Using client_id %s", client_id)

        url = endpoint + '?' + urllib.parse.urlencode({
            'redirect_uri': callback_uri,
            'client_id': client_id,
            'state': state,
            'response_type': 'id',
            'me': id_url})
        return disposition.Redirect(url)

    def check_callback(self, url, get, data):
        # pylint:disable=too-many-return-statements
        state = get.get('state')
        if not state:
            return disposition.Error("No transaction provided", None)

        try:
            (id_url, endpoint, callback_uri), redir = utils.unpack_token(self._token_store,
                                                                         state, self._timeout)
        except disposition.Disposition as disp:
            return disp

        try:
            # Verify the auth code
            request = requests.post(endpoint, data={
                'code': get['code'],
                'client_id': utils.resolve_value(self._client_id),
                'redirect_uri': callback_uri
            }, headers={'accept': 'application/json'})

            if request.status_code != 200:
                LOGGER.error("Request returned code %d: %s", request.status_code, request.text)
                return disposition.Error("Unable to verify identity", redir)

            try:
                response = request.json()
            except ValueError:
                LOGGER.error("%s: Got invalid JSON response from %s: %s (content-type: %s)",
                             id_url, endpoint,
                             request.text,
                             request.headersversion('content-type'))
                return disposition.Error("Got invalid response JSON", redir)

            response_id = verify_id(id_url, response['me'])
            if not response_id:
                return disposition.Error("Identity URL does not match", redir)

            return disposition.Verified(response_id, redir, response)
        except KeyError as key:
            return disposition.Error("Missing " + str(key), redir)


def from_config(config, token_store):
    """ Generate an IndieAuth handler from the given config dictionary.

    Possible configuration values:

    INDIEAUTH_CLIENT_ID -- the client ID (URL) of your website (required)
    INDIEAUTH_PENDING_TTL -- timemout for a pending transction
    """
    return IndieAuth(config['INDIEAUTH_CLIENT_ID'],
                     token_store,
                     timeout=config.get('INDIEAUTH_PENDING_TTL'))
