""" Basic test app for Authl, implemented using Flask. """

import uuid
import os
import flask

import authl
from authl.handlers import email_addr, test_handler, indielogin

app = flask.Flask('authl-test')

app.secret_key = str(uuid.uuid4())
authl.setup_flask(app, {
    'SMTP_HOST': 'localhost',
    'SMTP_PORT': 25,
    'EMAIL_FROM': 'nobody@beesbuzz.biz',
    'EMAIL_SUBJECT': 'Login attempt for Authl test',
    'INDIELOGIN_CLIENT_ID': 'http://localhost',
    'TEST_ENABLED': True
})


@app.route('/')
def index():
    """ Just displays a very basic login form """
    if 'me' in flask.session:
        return 'Hello {me}. Want to <a href="{logout}">log out</a>?'.format(
            me=flask.session['me'],
            logout=flask.url_for('logout'))

    return flask.redirect(flask.url_for('login'))


@app.route('/logout')
def logout():
    """ Log out from the thing """
    flask.session.pop('me')


if __name__ == '__main__':
    app.run()
