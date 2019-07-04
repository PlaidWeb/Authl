""" Basic test app for Authl, implemented using Flask. """

import uuid
import os
import flask

import authl
from authl.handlers import email_addr, test_handler, indielogin

app = flask.Flask('authl-test')

if os.environ.get('SMTP_SERVER') and os.environ.get('SMTP_PORT'):
    email_handler = email_addr.simple_sendmail(
        email_addr.smtplib_connector(os.environ.get('SMTP_SERVER'),
                                     os.environ.get('SMTP_PORT'),
                                     use_ssl='SMTP_USE_SSL' in os.environ),
        'nobody@beesbuzz.biz', 'Login attempted')
else:
    email_handler = print

auth = authl.Authl([
    email_addr.EmailAddress(str(uuid.uuid4()),
                            email_handler,
                            notify_cdata="Check your email"),
    test_handler.TestHandler(),
    indielogin.IndieLogin('http://localhost/')
])


@app.route('/')
def index():
    """ Just displays a very basic login form """
    return '''
    <html><body><form method="POST" action="{login}">
    <input type="text" name="id" placeholder="you@example.com">
    <input type="submit" value="go!">
    </form>
    </body></html>
    '''.format(login=flask.url_for('login'))


def handle_disposition(d):
    from authl import disposition
    if isinstance(d, disposition.Redirect):
        return flask.redirect(d.url)
    if isinstance(d, disposition.Verified):
        return "It worked! Hello {user}".format(user=d.identity)
    if isinstance(d, disposition.Notify):
        return d.cdata
    if isinstance(d, disposition.Error):
        return "Failure: {msg}".format(msg=d.message), 403
    return "what happen", 500


@app.route('/login', methods=['POST'])
def login():
    from flask import request

    url = request.form['id']
    handler, hid = auth.get_handler_for_url(url)

    return handle_disposition(
        handler.initiate_auth(request.form['id'],
                              flask.url_for('callback', hid=hid, _external=True)))


@app.route('/cb/<int:hid>')
def callback(hid, methods=['GET', 'POST']):
    from flask import request

    handler = auth.get_handler_by_id(hid)
    return handle_disposition(handler.check_callback(request.url, request.args, request.form))


if __name__ == '__main__':
    app.run()
