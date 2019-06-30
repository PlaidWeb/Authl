import uuid
import flask

import authl
from authl.handlers import email, test_handler

app = flask.Flask('authl-test')

auth = authl.Authl([
    email.Email(str(uuid.uuid4()), print),
    test_handler.TestHandler()
])


@app.route('/')
def index():
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
        return d.message
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
def callback(hid):
    from flask import request

    handler = auth.get_handler(hid)
    return handle_disposition(handler.check_callback(request.url, request.args, request.form))


if __name__ == '__main__':
    app.run()
