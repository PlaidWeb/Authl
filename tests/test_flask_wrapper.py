""" Tests for the Flask wrapper """
# pylint:disable=missing-docstring,duplicate-code

import json
import logging
import unittest.mock

import flask
from bs4 import BeautifulSoup

import authl.flask
from authl import disposition

from . import TestHandler

LOGGER = logging.getLogger(__name__)


def test_url_tester():
    app = flask.Flask(__name__)
    authl.flask.setup(app, {'TEST_ENABLED': True}, tester_path='/test')

    with app.test_request_context('http://example.site/'):
        test_url = flask.url_for('authl.test')

    with app.test_client() as client:
        assert json.loads(client.get(test_url).data) is None
        assert json.loads(client.get(test_url + '?url=nope').data) is None
        assert json.loads(client.get(test_url + '?url=test:foo').data) == {
            "name": "Loopback",
            "url": "test:foo"
        }


def test_dispositions_and_hooks():

    class InvalidDisposition(disposition.Disposition):
        pass

    class Dispositioner(TestHandler):
        def handles_url(self, url):
            return url

        @property
        def cb_id(self):
            return 'hi'

        def initiate_auth(self, id_url, callback_uri, redir):
            if id_url == 'redirect':
                return disposition.Redirect('http://example.com/')
            if id_url == 'verify':
                return disposition.Verified('verified://', redir)
            if id_url == 'notify':
                return disposition.Notify(redir)
            if id_url == 'error':
                return disposition.Error('something', redir)
            if id_url == 'invalid':
                return InvalidDisposition()
            raise ValueError("nope")

    notify_render = unittest.mock.Mock(return_value="notified")
    login_render = unittest.mock.Mock(return_value="login form")
    on_verified = unittest.mock.Mock(return_value="verified")

    app = flask.Flask(__name__)
    app.secret_key = __name__

    instance = authl.flask.setup(app, {},
                                 session_auth_name=None,
                                 notify_render_func=notify_render,
                                 login_render_func=login_render,
                                 on_verified=on_verified)
    instance.add_handler(Dispositioner())

    with app.test_request_context('http://example.site/'):
        login_url = flask.url_for('authl.login', _external=True)

    with app.test_client() as client:
        assert client.get(login_url + '?me=redirect').headers['Location'] == 'http://example.com/'

    with app.test_client() as client:
        assert client.get(
            login_url + '/blob?me=verify').data == b'verified'

    with app.test_client() as client:
        assert client.get(login_url + '/bobble?me=notify').data == b'notified'
        notify_render.assert_called_with('/bobble')

    with app.test_client() as client:
        assert client.get(login_url + '/chomp?me=error').data == b"login form"
        login_render.assert_called_with(login_url=flask.url_for('authl.login', redir='chomp'),
                                        test_url=None,
                                        auth=instance,
                                        id_url='error',
                                        error='something',
                                        redir='/chomp'
                                        )

    with app.test_client() as client:
        assert client.get(login_url + '/chomp?me=invalid').status_code == 500


def test_login_rendering():
    app = flask.Flask(__name__)
    authl.flask.setup(app, {}, stylesheet="/what.css")
    with app.test_request_context('https://foo.bar/'):
        login_url = flask.url_for('authl.login')

    with app.test_client() as client:
        soup = BeautifulSoup(client.get(login_url).data, 'html.parser')
        assert soup.find('link', rel='stylesheet', href='/what.css')

    with app.test_client() as client:
        assert client.get(login_url + '?asset=css').headers['Content-Type'] == 'text/css'
        assert client.get(login_url + '?asset=nonsense').status_code == 404


def test_default_hooks():
    sendmail = unittest.mock.Mock(return_value=None)

    app = flask.Flask(__name__)
    app.secret_key = __name__

    authl.flask.setup(app, {
        'TEST_ENABLED': True,
        'EMAIL_SENDMAIL': sendmail,
        'EMAIL_CHECK_MESSAGE': 'check yr email'})

    with app.test_client() as client:
        soup = BeautifulSoup(client.get('/login').data, 'html.parser')
        assert soup.find('input', type='url')

    with app.test_client() as client:
        soup = BeautifulSoup(client.get('/login?me=test:error').data, 'html.parser')
        assert soup.find('div', {'class': 'error'})

    with app.test_client() as client:
        soup = BeautifulSoup(client.get('/login?me=unknown://').data, 'html.parser')
        error = soup.find('div', {'class': 'error'})
        assert error.text.strip() == 'Unknown authorization method'

    with app.test_client() as client:
        assert client.get('/login?me=test:success')
        assert flask.session['me'] == 'test:success'

    with app.test_client() as client:
        soup = BeautifulSoup(client.get('/login?me=mailto:foo@bar').data, 'html.parser')
        sendmail.assert_called()
        message = soup.find('div', {'id': 'notify'})
        assert message.text.strip() == 'check yr email'


def test_callbacks():
    class CallbackHandler(TestHandler):
        @property
        def cb_id(self):
            return 'foo'

        def check_callback(self, url, get, data):
            LOGGER.info('url=%s get=%s data=%s', url, get, data)
            if 'me' in get:
                return disposition.Verified('get://' + get['me'], None)
            if 'me' in data:
                return disposition.Verified('data://' + data['me'], None)
            raise disposition.Error('nope', None)

    app = flask.Flask(__name__)
    app.secret_key = __name__
    instance = authl.flask.setup(app, {})
    instance.add_handler(CallbackHandler())

    with app.test_client() as client:
        assert client.get('/cb/foo?me=yumyan')
        assert flask.session['me'] == 'get://yumyan'
    with app.test_client() as client:
        assert client.post('/cb/foo', data={'me': 'hammerpaw'})
        assert flask.session['me'] == 'data://hammerpaw'
    with app.test_client() as client:
        soup = BeautifulSoup(client.get('/cb/foo').data, 'html.parser')
        error = soup.find('div', {'class': 'error'})
        assert error.text.strip() == 'nope'
    with app.test_client() as client:
        soup = BeautifulSoup(client.get('/cb/bar').data, 'html.parser')
        error = soup.find('div', {'class': 'error'})
        assert error.text.strip() == 'Invalid handler'


def test_client_id():
    app = flask.Flask(__name__)
    authl.flask.setup(app, {})
    with app.test_request_context('https://foo.bar/baz/'):
        assert authl.flask.client_id() == 'https://foo.bar'
