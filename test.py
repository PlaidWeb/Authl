""" Basic test app for Authl, implemented using Flask. """

import uuid
import flask

import authl

app = flask.Flask('authl-test')

app.secret_key = str(uuid.uuid4())
authl.setup_flask(
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
    print(flask.session)
    if 'me' in flask.session:
        return 'Hello {me}. Want to <a href="{logout}">log out</a>?'.format(
            me=flask.session['me'], logout=flask.url_for('logout', redir=flask.request.full_path)
        )

    return 'You are not logged in. Want to <a href="{login}">log in</a>?'.format(
        login=flask.url_for('login', redir=flask.request.full_path))


@app.route('/logout/<redir>')
def logout(redir=''):
    """ Log out from the thing """
    print('logout',redir)
    flask.session.clear()
    return flask.redirect(redir or '/')


if __name__ == '__main__':
    app.run()
