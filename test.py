import uuid
import flask

from authl.handlers import email
from authl import disposition

app = flask.Flask('email test')

h = email.Email(str(uuid.uuid4()), print)


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
    return handle_disposition(h.initiate_auth(request.form['id'],
                                              flask.url_for('callback', _external=True)))


@app.route('/cb')
def callback():
    from flask import request
    return handle_disposition(h.check_callback(request.url, request.args, request.form))


if __name__ == '__main__':
    app.run()
