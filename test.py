""" Basic test app for Authl, implemented using Flask.

Run it locally with:

    pipenv install --dev
    FLASK_APP=test pipenv run flask run

 """

import uuid
import logging

import flask
import authl.flask

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

app = flask.Flask('authl-test')

app.secret_key = str(uuid.uuid4())
authl.flask.setup(
    app,
    {
        'SMTP_HOST': 'localhost',
        'SMTP_PORT': 25,
        'EMAIL_FROM': 'nobody@beesbuzz.biz',
        'EMAIL_SUBJECT': 'Login attempt for Authl test',
        'INDIELOGIN_CLIENT_ID': 'http://localhost',
        'TEST_ENABLED': True,
    },
)


@app.route('/')
@app.route('/some-page')
def index():
    """ Just displays a very basic login form """
    LOGGER.info("Session: %s", flask.session)
    LOGGER.info("Request path: %s", flask.request.path)

    if 'me' in flask.session:
        return 'Hello {me}. Want to <a href="{logout}">log out</a>?'.format(
            me=flask.session['me'], logout=flask.url_for('logout', redir=flask.request.path[1:])
        )

    return 'You are not logged in. Want to <a href="{login}">log in</a>?'.format(
        login=flask.url_for('login', redir=flask.request.path[1:]))


@app.route('/logout/')
@app.route('/logout/<path:redir>')
def logout(redir=''):
    """ Log out from the thing """
    LOGGER.info("Logging out")
    LOGGER.info("Redir: %s", redir)
    LOGGER.info("Request path: %s", flask.request.path)

    flask.session.clear()
    return flask.redirect('/' + redir)


if __name__ == '__main__':
    app.run()
