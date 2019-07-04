# Authl
A library for managing federated identity

## Current state

Currently supported:

* Directly authenticating against email
* Federated authentication against [IndieLogin](https://indielogin.com)
* Test/loopback authentication

## Design goals

High-level goal: Make it easy to provide federated identity to Python 3-based web apps (with a particular focus on [Publ](https://github.com/PlaidWeb/Publ))

This library should enable the following:

* Given a URL, determine whether an identity can be established against that URL
* Provide multiple identity backends for different URL schemata, including but not limited to:
    * OpenID 1.x
    * IndieAuth
    * Email
    * Various OAuth providers (twitter, facebook, etc.)
    * Mastodon
    * Local username/password
* Each backend should be optional and configurable
* Provide default (optional) Flask endpoints for the various endpoints (URL validation, success callbacks, etc.)

## Roadmap

Rough expected order of implementation:

1. ~~Email magic links (which provides access for basically everyone)~~ DONE
1. ~~IndieAuth (possibly using IndieLogin.com for the hard parts)~~ DONE
1. OpenID 1.x (which provides access for Dreamwidth, Wordpress, Launchpad, and countless other site users)
1. Everything else

## Rationale

Identity is hard, and there are so many competing standards which try to be the be-all end-all Single Solution. Many of them are motivated by their own politics; OAuth wants lock-in to silos, IndieAuth wants every user to self-host their own identity fully and not support silos at all, etc., and users just want to be able to log in with the social media they're already using (siloed or not).

Any solution which requires all users to have a certain minimum level of technical ability is not a workable solution.

All of these solutions are prone to the so-called "NASCAR problem" where every supported login provider needs its own UI. But being able to experiment with a more unified UX might help to fix some of that.

## Usage

This is just in its early experimental phase and the API is subject to change. However, if you would like to use it anyway, see `test.py` in the project source, which provides a minimal Flask app that does nothing but ask for an identity to log in as, and validates that identity.

The basic flow is as follows:

1. Create an Authl object with your configured handlers

    At present, the only useful handlers are `email_addr` and `indieauth`.

2. Make endpoints for initiation and progress callbacks (`/login` and `/cb` in `test.py`)

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
    * `Notify`: return a notification to the user that they must take another action (e.g. checking their email)
    * `Verified`: indicates that the user has been verified; set a session cookie (or whatever) and forward them along to their intended destination
    * `Error`: An error occurred; return it to the user as appropriate

### Flask example

Note: this is untested. Eventually there will be a more fleshed-out sample site to use for an example.

```python
import uuid
import flask
import authl
from authl.handlers import email_addr, indielogin

app = flask.Flask(__name__)

# Make sure the app.secret_key is set to something secret!
# see http://flask.pocoo.org/docs/1.0/quickstart/#sessions for more info
app.secret_key = uuid.uuid4()

auth = authl.Authl([
    # email handler that uses localhost to send messages
    email_addr.EmailAddress(app.secret_key,
        email_addr.simple_sendmail(
            email_addr.smtplib_connector('localhost', 25, use_ssl=False),
            'nobody@example.com', 'Login requested to example.com'),
        {'message':"Check your email"}
    ),

    # IndieLogin handler using indielogin.com
    indielogin.IndieLogin('http://example.com',
        instance='https://indielogin.com')
])

@app.route('/login/<path:redir>')
def login(redir):
    from flask import request

    if 'me' in request.args:
        me_url = request.args['me']
        handler, hid = auth.get_handler_for_url(me_url)
        if handler:
            cb_url = flask.url_for('login_cb', hid=hid, redir=redir, _external=True)
            return handle_disposition(handler.initiate_auth(me_url, cb_url), redir)

        # No handler found, so flash an error message to login_form
        flask.flash("Unknown authorization method")

    return render_template('login_form.html')

@app.route('/_cb/<int:hid>/<path:redir>')
def login_cb(hid, redir):
    from flask import request

    handler = auth.get_handler_by_id(hid)
    return handle_disposition(handler.check_callback(request.url, request.args, request.form), redir)

def handle_disposition(d, redir):
    from authl import disposition

    # A simple redirection
    if isinstance(d, disposition.Redirect):
        return flask.redirect(d.url)

    # The user is verified; log them in
    if isinstance(d, disposition.Verified):
        flask.session['who'] = d.identity
        return flask.redirect(redir)

    # The user needs to take some additional action
    if isinstance(d, disposition.Notify):
        return render_template('login_notify.html', cdata=d.cdata)

    # The user's login failed
    if isinstance(d, disposition.Error):
        return render_template('login_form.html', error=d.message), 403

    # Something weird happened
    return "Unknown disposition", 500


@app.route('/some-protected-page')
def protected_page():
    # this could also be wrapped up in a Flask-Login decorator or the like
    if 'who' not in flask.session or flask.session['who'] not in authorized_users:
        return flask.redirect(url_for('login', redir=flask.request.full_path))

    return "It's a secret to everyone!"

```