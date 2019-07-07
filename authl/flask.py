""" Flask wrapper for Authl """

from . import from_config, disposition


def setup(app,
          config,
          login_name='login',
          login_path='/login',
          login_render_func=None,
          notify_render_func=None,
          callback_name='_authl_callback',
          callback_path='/_cb',
          session_auth_name='me',
          force_ssl=False
          ):
    """ Setup Authl to work with a Flask application.

    The Flask application should be configured with a secret_key before this
    function is called.

    Arguments:

    app -- the application to attach to
    config -- Configuration directives for Authl's handlers. See from_config
        for more information.
    login_name -- The endpoint name for the login handler, for flask.url_for()
    login_path -- The mount point of the login route
    login_render_func -- The function to call to render the login page; if not
        specified a default will be provided. It must take an argument named
        'redir' (for the redir parameter to pass along to flask.url_for) and
        should support Flask message flashing.
    callback_name -- The endpoint name for the callback handler, for
        flask.url_for()
    callback_path -- The mount point of the callback handler
    session_auth_name -- The session parameter to use for the authenticated user
    force_ssl -- Whether to force authentication to switch to an SSL connection
    """
    # pylint:disable=too-many-arguments,too-many-locals

    import flask

    auth = from_config(config, app.secret_key)
    url_scheme = 'https' if force_ssl else None

    def set_cache(age):
        def decorator(func):
            def wrapped_func(*args, **kwargs):
                response = flask.make_response(func(*args, **kwargs))
                response.cache_control.max_age = age
                return response
            return wrapped_func
        return decorator

    @set_cache(0)
    def handle_disposition(disp, redir):

        if isinstance(disp, disposition.Redirect):
            # A simple redirection
            return flask.redirect(disp.url)

        if isinstance(disp, disposition.Verified):
            # The user is verified; log them in
            flask.session.permanent = True
            flask.session[session_auth_name] = disp.identity
            return flask.redirect('/' + redir)

        if isinstance(disp, disposition.Notify):
            # The user needs to take some additional action
            return render_notify(disp.cdata)

        if isinstance(disp, disposition.Error):
            # The user's login failed
            flask.flash(disp.message)
            return render_login_form(redir=redir)

        # unhandled disposition
        import werkzeug.exceptions as http_error
        raise http_error.InternalServerError("Unknown disposition type " + type(disp))

    @set_cache(0)
    def render_notify(cdata):
        if notify_render_func:
            return notify_render_func(cdata)

        return str(cdata)

    @set_cache(0)
    def render_login_form(**kwargs):
        if login_render_func:
            return login_render_func(**kwargs)

        # Default template that shows a login form and flashes all pending messages
        return flask.render_template_string("""<!DOCTYPE html>
<html><head>
<title>Login</title>
</head><body>
{% with messages = get_flashed_messages() %}
  {% if messages %}
  <p>The following errors occurred:</p>
    <ul class="flashes">
    {% for message in messages %}
      <li>{{ message }}</li>
    {% endfor %}
    </ul>
  {% endif %}
{% endwith %}

<form method="GET" action="{{login_url}}">
<input type="text" name="me" placeholder="you@example.com">
<input type="submit" value="go!">
</form>
</body></html>
""", login_url=flask.url_for(login_name, redir=kwargs.get('redir'), _scheme=url_scheme))

    def login(redir=''):
        from flask import request

        if 'me' in request.args:
            me_url = request.args['me']
            handler, hid = auth.get_handler_for_url(me_url)
            if handler:
                cb_url = flask.url_for(callback_name, hid=hid, redir=redir, _external=True,
                                       _scheme=url_scheme)
                return handle_disposition(handler.initiate_auth(me_url, cb_url), redir)

            # No handler found, so flash an error message to login_form
            flask.flash('Unknown authorization method')

        return render_login_form(redir=redir)

    def callback(hid, redir=''):
        from flask import request

        handler = auth.get_handler_by_id(hid)
        return handle_disposition(
            handler.check_callback(request.url, request.args, request.form), redir
        )

    for sfx in ['', '/', '/<path:redir>']:
        app.add_url_rule(login_path + sfx, login_name, login)
        app.add_url_rule(callback_path + '/<int:hid>' + sfx, callback_name, callback)
