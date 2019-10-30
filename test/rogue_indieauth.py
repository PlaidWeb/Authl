""" A rogue IndieAuth authorization_endpoint test

https://github.com/PlaidWeb/Authl/issues/47

Run with e.g.

FLASK_APP=test/rogue_indieauth.py pipenv run flask run -p 6789
"""

import urllib.parse

import flask
import itsdangerous

app = flask.Flask(__name__)  # pylint:disable=invalid-name

sign = itsdangerous.URLSafeSerializer('key')  # pylint:disable=invalid=-name


@app.route('/', methods=('GET', 'POST'))
@app.route('/<path:path>', methods=('GET', 'POST'))
def endpoint(path=''):
    get = flask.request.args
    post = flask.request.form
    if 'code' in post:
        return flask.jsonify({
            'me': sign.loads(post['code']),
            'scope': 'read',
        })

    if 'me' in post:
        redir = post['redirect_uri']
        args = urllib.parse.urlencode({
            'code': sign.dumps(post['me']),
            'state': post.get('state'),
            'me': post['me']
        })

        return flask.redirect(redir + ('&' if '?' in redir else '?') + args)

    if 'redirect_uri' in get:
        return flask.render_template_string('''<!DOCTYPE html>
<html><head>
<title>rogue login</title>
</head><body>
<form action="{{url_for('endpoint',path=path)}}" method="POST">
<input type="hidden" name="state" value="{{get.state}}">
<input type="hidden" name="redirect_uri" value="{{get.redirect_uri}}">
Who do you want to be today? <input type="text" name="me" value="{{get.me}}">
<input type="submit" value="Go">
</form></body>
</html>
''', get=get, path=path)

    return flask.render_template_string('''<!DOCTYPE html>
<html><head>
<title>rogue access point</title>
<link rel="authorization_endpoint" href="{{url_for('endpoint',path=path,_external=True)}}">
</head><body>
<p>
Use <code>{{url_for('endpoint',path=path,_external=True)}}</code> as the test identity.
</p>
</body></html>''', path=path)
