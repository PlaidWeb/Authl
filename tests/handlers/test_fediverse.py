""" Tests of the Fediverse handler """
# pylint:disable=missing-docstring

import json
import logging
import urllib.parse

import requests_mock

from authl import disposition, tokens
from authl.handlers import fediverse

from . import parse_args

LOGGER = logging.getLogger(__name__)


def test_basic_flow():
    store = {}

    client = {
        "id": "746573",
        "name": "blop",
        "website": "https://myapp.example",
        "client_id": "cli12345",
        "client_secret": "cls54321",
    }
    handler = fediverse.Fediverse('blop', tokens.DictStore(store))

    def mock_client(request, _):
        args = urllib.parse.parse_qs(request.text)
        client['redirect_uri'] = args['redirect_uris'][0]
        return json.dumps(client)

    def mock_token(request, _):
        args = urllib.parse.parse_qs(request.text)
        assert args['client_id'] == [client['client_id']]
        assert args['client_secret'] == [client['client_secret']]
        assert args['scope'] == ['read:accounts']
        assert args['redirect_uri'] == ['FIXME']

    assert handler.service_name == 'Fediverse'
    assert 'Fediverse' in handler.description
    assert handler.url_schemes
    assert handler.cb_id == 'fv'
    assert len(handler.logo_html) == 2

    with requests_mock.Mocker() as mock:
        mock.get('https://fedi.example/api/v1/instance', text=json.dumps({
            'uri': 'fedi.example',
            'version': 'v1.2.3-bogus',
            'urls': {'streaming_api': 'wss://fedi.example/'},
        }))
        mock.post('https://fedi.example/api/v1/apps', text=mock_client)

        assert handler.handles_url('https://fedi.example/') == 'https://fedi.example'
        assert handler.handles_url('https://fedi.example/user/mew') == 'https://fedi.example/@mew'
        assert handler.handles_url('https://fedi.example/@moo') == 'https://fedi.example/@moo'
        assert not handler.handles_url('https://twitter.com/fluffy')
        assert not handler.handles_url('@fluffy@fedi.example')

        assert len(store) == 0
        res = handler.initiate_auth('https://fedi.example/@doug', 'https://cb/', '/after')
        LOGGER.debug(res)
        assert isinstance(res, disposition.Redirect)
        assert len(store) == 1

        assert res.url.startswith('https://fedi.example/oauth/authorize')

        # fake the user dialog
        args = parse_args(res.url)
        assert args['redirect_uri'].startswith('https://cb/')
        assert args['state'] in store

        mock.post('https://fedi.example/oauth/token', text=mock_token)
        res = handler.check_callback(args['redirect_uri'], args, {})

