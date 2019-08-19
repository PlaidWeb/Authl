""" Basic test app for Authl, implemented using Flask.

Run it locally with:

    pipenv install --dev
    FLASK_APP=test pipenv run flask run

 """

import logging
import os
import uuid

import flask

import authl.flask

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

app = flask.Flask('authl-test')

app.secret_key = str(uuid.uuid4())


def on_login(verified):
    LOGGER.info("Got login: %s", verified)
    if verified.identity == 'test:override':
        return "This user gets a special override"


authl.flask.setup(
    app,
    {
        'EMAIL_SENDMAIL': print,
        'EMAIL_FROM': 'nobody@example.com',
        'EMAIL_SUBJECT': 'Log in to authl test',
        'EMAIL_CHECK_MESSAGE': 'Use the link printed to the test console',

        'INDIEAUTH_CLIENT_ID': authl.flask.client_id,
        'INDIELOGIN_CLIENT_ID': authl.flask.client_id,

        'TEST_ENABLED': True,

        'MASTODON_NAME': 'authl testing',
        'MASTODON_HOMEPAGE': 'https://github.com/PlaidWeb/Authl',

        'TWITTER_CLIENT_KEY': os.environ.get('TWITTER_CLIENT_KEY'),
        'TWITTER_CLIENT_SECRET': os.environ.get('TWITTER_CLIENT_SECRET'),
    },
    tester_path='/check_url',
    on_verified=on_login
)


@app.route('/')
@app.route('/some-page')
def index():
    """ Just displays a very basic login form """
    LOGGER.info("Session: %s", flask.session)
    LOGGER.info("Request path: %s", flask.request.path)

    if 'me' in flask.session:
        return 'Hello {me}. Want to <a href="{logout}">log out</a>?'.format(
            me=flask.session['me'], logout=flask.url_for(
                'logout', redir=flask.request.path[1:])
        )

    return 'You are not logged in. Want to <a href="{login}">log in</a>?'.format(
        login=flask.url_for('authl.login', redir=flask.request.path[1:]))


@app.route('/logout/')
@app.route('/logout/<path:redir>')
def logout(redir=''):
    """ Log out from the thing """
    LOGGER.info("Logging out")
    LOGGER.info("Redir: %s", redir)
    LOGGER.info("Request path: %s", flask.request.path)

    flask.session.clear()
    return flask.redirect('/' + redir)
