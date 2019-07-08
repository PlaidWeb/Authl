# Authl
A library for managing federated identity

## About

Authl is intended to make it easy to add federated identity to Python-based web apps without requiring the creation of site-specific user accounts, but also without requiring the user to choose from a myriad of buttons or links to select any specific login provider.

All it should take is a single login form that asks for how the user wants to be identified.

## Current state

Currently supported authentication mechanisms:

* Directly authenticating against email using a magic link
* Federated authentication against [IndieLogin](https://indielogin.com)
* Federated authentcation against [Mastodon](https://joinmastodon.org)
* Test/loopback authentication for development purposes

It also provides an easy setup mechanism for use with [Flask](http://flask.pocoo.org).

## Rationale

Identity is hard, and there are so many competing standards which try to be the be-all end-all Single Solution. OAuth and OpenID Connect want lock-in to silos, IndieAuth wants every user to self-host their own identity site, and OpenID 1.x has fallen by the wayside. Meanwhile, users just want to be able to log in with the social media they're already using (siloed or not).

Any solution which requires all users to have a certain minimum level of technical ability is not a workable solution.

All of these solutions are prone to the so-called "[NASCAR problem](https://indieweb.org/NASCAR_problem)" where every supported login provider needs its own UI. But being able to experiment with a more unified UX might help to fix some of that.

## Usage

Basic usage is as follows:

1. Create an Authl object with your configured handlers

    This can be done by instancing individual handlers yourself, or you can use `authl.from_config`

2. Make endpoints for initiation and progress callbacks

    The initiation callback receives an identity string (email address/URL/etc.) from the user, queries Authl
    for the handler and its ID, and builds a callback URL for that handler to use. Typically you'll have a single
    callback endpoint that includes the handler's ID as part of the URL scheme.

    The callback endpoint needs to be able to receive a `GET` or `POST` request and use that to validate the
    returned data from the authorization handler.

    Your callback endpoint (and generated URL thereof) should also include whatever intended forwarding destination.

3. Handle the `authl.disposition` object types accordingly

    A `disposition` is what should be done with the agent that initiated the endpoint call. Currently there
    are the following:

    * `Redirect`: return an HTTP redirection to forward it along to another URL
    * `Notify`: return a notification to the user that they must take another action (e.g. check their email)
    * `Verified`: indicates that the user has been verified; set a session cookie (or whatever) and forward them along to their intended destination
    * `Error`: An error occurred; return it to the user as appropriate

## Flask usage

To make life easier with Flask, Authl provides an `authl.setup_flask` convenience function. You can use it from a Flask app with something like the below:

```python
import uuid
import logging

import flask
import authl.flask

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# Create a Flask application and give it a randomly-generated signing key
app = flask.Flask('authl-test')
app.secret_key = str(uuid.uuid4())

# Configure the default Flask endpoints
authl.flask.setup(
    app,
    {
        'SMTP_HOST': 'localhost',
        'SMTP_PORT': 25,
        'EMAIL_FROM': 'nobody@example.com',
        'EMAIL_SUBJECT': 'Login attempt for Authl test',
        'INDIELOGIN_CLIENT_ID': 'http://localhost',
        'MASTODON_NAME': 'Authl test site'
    },
)

# Here's a simple page handler which just shows a login link if you're logged out
# and vice versa
@app.route('/')
@app.route('/some-page')
def index():
    if 'me' in flask.session:
        return 'Hello {me}. Want to <a href="{logout}">log out</a>?'.format(
            me=flask.session['me'],
            logout=flask.url_for('logout', redir=flask.request.path[1:])
        )

    return 'You are not logged in. Want to <a href="{login}">log in</a>?'.format(
        login=flask.url_for('login', redir=flask.request.path[1:]))

# And here's a means of logging out
@app.route('/logout/')
@app.route('/logout/<path:redir>')
def logout(redir=''):
    flask.session.clear()
    return flask.redirect('/' + redir)
```

This will configure the Flask app to allow IndieLogin and email-based authentication (using the server's local sendmail), and use the default login endpoint of `/login/`. The `index()` endpoint handler always redirects logins and logouts back to the same page when you log in or log out (the `[1:]` is to trim off the initial `/` from the path). The logout handler simply clears the session and redirects back to the redirection path.

The above configuration uses Flask's default session lifetime of one month (this can be configured by setting `app.permanent_session_lifetime` to a `timedelta` object, e.g. `app.permanent_session_lifetime = datetime.timedelta(hours=20)`). Sessions will also implicitly expire whenever the application server is restarted, as `app.secret_key` is generated randomly at every startup.

