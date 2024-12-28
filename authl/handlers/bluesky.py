"""
Bluesky
=======

This handler allows third-party login through `Bluesky <https://bsky.social/>`.

This handler registers itself with a ``cb_id`` of ``"bsky"``.

Much of this implementation is adapted from ``python-oauth-web-app`` from the `Bluesky cookbook <https://github.com/bluesky-social/cookbook>`.

"""

import logging
import re
import time
import urllib.parse
from typing import Optional, Tuple
import json

import dns.resolver
import expiringdict
import requests
from requests_oauthlib import OAuth1, OAuth1Session

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)

HANDLE_REGEX = r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
DID_REGEX = r"^did:[a-z]+:[a-zA-Z0-9._:%-]*[a-zA-Z0-9._-]$"


def is_valid_handle(handle: str) -> bool:
    """ Returns whether this a valid bluesky handle """
    return re.match(HANDLE_REGEX, handle) is not None


def is_valid_did(did: str) -> bool:
    """ Returns whether this is a valid atproto DID """
    return re.match(DID_REGEX, did) is not None


def resolve_identity(atid: str) -> Tuple[str, str, dict]:
    """ Resolves an identity to a DID + handle + document """

    if is_valid_handle(atid):
        handle = atid

        did = resolve_handle(handle)
        if not did:
            LOGGER.info("Failed to resolve handle %s", handle)
            return None, None, None

        doc = resolve_did(did)
        if not doc:
            LOGGER.info("Failed to resolve DID %s", did)
            return None, None, None

        doc_handle = handle_from_doc(doc)
        if not doc_handle or doc_handle != handle:
            LOGGER.info("Handle %s did not match DID %s handle %s", doc_handle, did, handle)
        return did, handle, doc

    if is_valid_did(atid):
        did = atid
        doc = resolve_did(did)
        if not doc:
            LOGGER.info("Failed to resolve DID %s", did)
            return None, None, None

        handle = handle_from_doc(doc)
        if not handle:
            LOGGER.info("Could not get handle from DID %s", did)
            return None, None, None

        if resolve_handle(handle) != did:
            LOGGER.info("Handle %s did not match DID %s", handle, did)
            return None, None, None

        return did, handle, doc

    return None, None, None


def handle_from_doc(doc: dict) -> Optional[str]:
    """ Extract the handle from the identity document """
    for aka in doc.get("alsoKnownAs", []):
        if aka.startswith("at://"):
            handle = aka[5:]
            if is_valid_handle(handle):
                return handle
    return None


def resolve_handle(handle: str) -> Optional[str]:
    """ Resolve a DID from a handle """

    # first try TXT record
    try:
        for record in dns.resolver.resolve(f"_atproto.{handle}", "TXT"):
            val = record.to_text().replace('"', "")
            if val.startswith("did="):
                val = val[4:]
                if is_valid_did(val):
                    return val
    except Exception:
        pass

    # then try HTTP well-known
    wellknown = utils.request_url(f"https://{handle}/.well-known/atproto-did")
    if not wellknown or wellknown.status_code != 200:
        return None

    did = wellknown.text.split()[0]
    if not is_valid_did(did):
        return None

    return did


def resolve_did(did: str) -> Optional[dict]:
    """ Resolve a DID to a document """

    if did.startswith("did:plc:"):
        resp = utils.request_url(f"https://plc.directory/{did}")
        if resp.status_code != 200:
            return None
        return resp.json()

    if did.startswith("did:web:"):
        domain = did[8:]
        if not is_valid_handle(domain):
            return None

        resp = utils.request_url(f"https://{domain}/.well-known/did.json")
        if resp.status_code != 200:
            return None
        return resp.json()

    return None


class Bluesky(Handler):
    """ Supports Bluesky/ATProto """

    @property
    def service_name(self):
        return 'Bluesky'

    @property
    def url_schemes(self):
        return [('%', 'example.bsky.social'),
                ('did:%', 'did'),
                ]

    @property
    def description(self):
        return """Supports login via <a href="https://bsky.social/">Bluesky</a>."""

    @property
    def cb_id(self):
        return 'bsky'

    @property
    def logo_html(self):
        return [(utils.read_icon('bluesky.svg'), 'Bluesky')]

    def handles_url(self, url):
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc in ('bsky.app', 'bsky.social'):
            return self.generic_url

        did, handle, doc = resolve_identity(url)
        return handle

    @property
    def generic_url(self):
        return "https://bsky.app/"



    def __init__(self,
            website_name: str,
             token_store: tokens.TokenStore,
             make_data_url: Callable[str],
             timeout: Optional[int] = None,
             homepage: Optional[str] = None):
        """
        :param str website_name: The name of the website
        :param str website_url: The URL for the website, as a string or a callable function. Flask users can use `py:func:flask.client_id`.

        :param token_store: Storage for the tokens.

        :param int timeout: Maximum time to wait for login to complete
            (default: 600)
        """
        self._website_name = website_name
        self._homepage = homepage
        self._make_data_url = make_data_url
        self._website_url = website_url
        self._token_store = token_store
        self._timeout = timeout or 600

    def get_data(self, callback_url, path, get, data):
        def jsonify(data):
            return disposition.Data(json.dumps(data),
                {'Content-Type': 'application/json'})

        if path == 'client_info.json':
            return jsonify({
                "client_id": self._make_data_url(self.cb_id,
                    'client_info.json'),
                "dpop_bound_access_tokens": True,
                "application_type": "web",
                "redirect_uris": [callback_url],
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "scope": "atproto transition:generic",
                "client_name": self._website_name,
                "client_uri": self._website_url,
            })

        return disposition.Error("Invalid request", '')

    def initiate_auth(self, id_url, callback_uri, redir):
        did, handle, doc = resolve_identity(id_url)




def from_config(config, token_storage tokens.TokenStore, instance):
    """ Generate a Bluesky handler from the given config dictionary.

    :param dict config: Configuration values; relevant keys:

        * ``BLUESKY_NAME``: The name of the website
        * ``BLUESKY_HOMEPAGE``: The URL of the website
        * ``BLUESKY_TIMEOUT``: The maximum time to wait for login to complete

    :param tokens.TokenStore token_store: The authentication token storage

    :param Authl instance: The Authl instance (needed for configuration)
    """

    return Bluesky(config['BLUESKY_NAME'], token_store,
        timeout=config.get('BLUESKY_TIMEOUT'),
        homepage=config.get('BLUESKY_HOMEPAGE'),
        make_data_url=instance.make_data_url)

