""" Basic test app for Authl, implemented using Flask.

Run it locally with:

    poetry install --dev
    FLASK_APP=test poetry run flask run

 """

import logging
import os

import flask

import authl.flask

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

app = flask.Flask('authl-test')
app.secret_key = "testing isn't secret"


def on_login(verified):
    LOGGER.info("Got login: %s", verified)
    flask.session['profile'] = verified.profile
    if verified.identity == 'test:override':
        return "This user gets a special override"


authl.flask.setup(
    app,
    {
        'EMAIL_SENDMAIL': print,
        'EMAIL_FROM': 'nobody@example.com',
        'EMAIL_SUBJECT': 'Log in to authl test',
        'EMAIL_CHECK_MESSAGE': 'Use the link printed to the test console',
        'EMAIL_EXPIRE_TIME': 60,

        'INDIEAUTH_CLIENT_ID': authl.flask.client_id,
        'INDIEAUTH_PENDING_TTL': 10,

        'TEST_ENABLED': True,

        'FEDIVERSE_NAME': 'authl testing',
        'FEDIVERSE_HOMEPAGE': 'https://github.com/PlaidWeb/Authl',

        'TWITTER_CLIENT_KEY': os.environ.get('TWITTER_CLIENT_KEY'),
        'TWITTER_CLIENT_SECRET': os.environ.get('TWITTER_CLIENT_SECRET'),
        'TWITTER_REQUEST_EMAIL': True,
    },
    tester_path='/check_url',
    on_verified=on_login
)


@app.route('/logout/')
@app.route('/logout/<path:redir>')
def logout(redir=''):
    """ Log out from the thing """
    LOGGER.info("Logging out")
    LOGGER.info("Redir: %s", redir)
    LOGGER.info("Request path: %s", flask.request.path)

    flask.session.clear()
    return flask.redirect('/' + redir)


@app.route('/')
@app.route('/page')
@app.route('/page/')
@app.route('/page/<path:page>')
def index(page=''):
    """ Just displays a very basic login form """
    LOGGER.info("Session: %s", flask.session)
    LOGGER.info("Request path: %s", flask.request.path)

    if 'me' in flask.session:
        return flask.render_template_string(
            r"""
<p>Hello {{profile.name or me}}.
Want to <a href="{{url_for('logout', redir=request.path[1:])}}">log out</a>?</p>

{% if profile %}
<p>Profile data:</p>
<ul>
{% for k,v in profile.items() %}
<li>{{k}}: {{v}}</li>
{% endfor %}
</ul>
{% endif %}""",
            me=flask.session['me'],
            profile=flask.session.get('profile')
        )

    return 'You are not logged in. Want to <a href="{login}">log in</a>?'.format(
        login=flask.url_for('authl.login', redir=flask.request.path[1:]))
