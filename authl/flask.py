""" Flask wrapper for Authl """

import functools
import json
import logging
import os
import urllib.parse

import werkzeug.exceptions as http_error

from . import disposition, from_config, utils

LOGGER = logging.getLogger(__name__)


def setup(app,
          config,
          login_name='authl.login',
          login_path='/login',
          callback_name='authl.callback',
          callback_path='/cb',
          tester_name='authl.test',
          tester_path=None,
          login_render_func=None,
          notify_render_func=None,
          session_auth_name='me',
          force_ssl=False,
          stylesheet=None,
          on_verified=None,
          make_permanent=True
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
    callback_name -- The endpoint name for the callback handler, for
        flask.url_for()
    callback_path -- The mount point of the callback handler
    tester_name -- The endpoint name for the URL tester, for flask.url_for()
    tester_path -- The mount point of the URL tester
    login_render_func -- The function to call to render the login page; if not
        specified a default will be provided.
    notify_render_func -- The function to call to render the user notification
        page; if not specified a default will be provided.
    session_auth_name -- The session parameter to use for the authenticated user
    force_ssl -- Whether to force authentication to switch to an SSL connection
    stylesheet -- the URL to use for the default page stylesheet
    on_verified -- A function to call on successful login (called after
        setting the session value)
    make_permanent -- Whether a session should persist past the browser window
        closing

    The login_render_func takes the following arguments:

        login_url -- the URL to use for the login form
        auth -- the Authl object

    If login_render_func returns a false value, the default login form will be
    used instead. This is useful for providing a conditional override, or as a
    rudimentary hook for analytics on the login flow or the like.

    The render_notify_func takes the following arguments:

        cdata -- the client data for the handler

    The on_verified function receives the disposition.Verified object, and may
    return a Flask response of its own, ideally a flask.redirect(). This can be
    used to capture more information about the user (such as their display name)
    or to redirect certain users to an administrative screen of some sort.

    The login endpoint takes a query parameter of 'me' which is the URL to
    authenticate against.

    The URL tester endpoint takes a query parameter of 'url' which is the URL
    to check. It returns a JSON object that describes the detected handler, with
    the following attributes:

        name -- the service name
        url -- a canonicized version of the URL

    The URL tester endpoint will only be mounted if tester_path is specified.

    Return value: the configured Authl instance

    """
    # pylint:disable=too-many-arguments,too-many-locals

    import flask

    instance = from_config(config, app.secret_key)
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
            LOGGER.info("Successful login: %s", disp.identity)
            flask.session.permanent = make_permanent
            flask.session[session_auth_name] = disp.identity

            if on_verified:
                response = on_verified(disp)
                if response:
                    return response

            return flask.redirect('/' + redir)

        if isinstance(disp, disposition.Notify):
            # The user needs to take some additional action
            return render_notify(disp.cdata)

        if isinstance(disp, disposition.Error):
            # The user's login failed
            flask.flash(disp.message)
            return render_login_form(redir=redir)

        # unhandled disposition
        raise http_error.InternalServerError("Unknown disposition type " + type(disp))

    @functools.lru_cache(8)
    def load_template(filename):
        return utils.read_file(os.path.join(os.path.dirname(__file__), 'flask_templates', filename))

    @set_cache(0)
    def render_notify(cdata):
        if notify_render_func:
            result = notify_render_func(cdata)
            if result:
                return result

        return flask.render_template_string(load_template('notify.html'),
                                            cdata=cdata,
                                            stylesheet=get_stylesheet())

    @set_cache(0)
    def render_login_form(redir):
        login_url = flask.url_for(login_name,
                                  redir=redir,
                                  _scheme=url_scheme,
                                  _external=bool(url_scheme))
        if login_render_func:
            result = login_render_func(login_url=login_url,
                                       auth=instance)
            if result:
                return result

        return flask.render_template_string(load_template('login.html'),
                                            login_url=login_url,
                                            stylesheet=get_stylesheet(),
                                            auth=instance)

    def login(redir=''):
        from flask import request

        if 'asset' in request.args:
            asset = request.args['asset']
            if asset == 'css':
                return load_template('authl.css'), {'Content-Type': 'text/css'}
            raise http_error.NotFound("Unknown asset " + asset)

        if 'me' in request.args:
            me_url = request.args['me']
            handler, hid, id_url = instance.get_handler_for_url(me_url)
            if handler:
                cb_url = flask.url_for(callback_name,
                                       hid=hid,
                                       redir=redir,
                                       _external=True,
                                       _scheme=url_scheme)
                return handle_disposition(handler.initiate_auth(id_url, cb_url), redir)

            # No handler found, so flash an error message to login_form
            flask.flash('Unknown authorization method')

        return render_login_form(redir=redir)

    def callback(hid, redir=''):
        from flask import request

        handler = instance.get_handler_by_id(hid)
        return handle_disposition(
            handler.check_callback(request.url, request.args, request.form), redir
        )

    for sfx in ['', '/', '/<path:redir>']:
        app.add_url_rule(login_path + sfx, login_name, login)
        app.add_url_rule(callback_path + '/<int:hid>' + sfx, callback_name, callback)

    def get_stylesheet():
        if stylesheet is None:
            return flask.url_for(login_name, asset='css')
        return stylesheet

    def find_service():
        from flask import request

        url = request.args.get('url')
        if not url:
            return json.dumps(None)

        handler, _, canon_url = instance.get_handler_for_url(url)
        if handler:
            return json.dumps({'name': handler.service_name,
                               'url': canon_url})

        return json.dumps(None)

    if tester_path:
        app.add_url_rule(tester_path, tester_name, find_service)

    return instance


def client_id():
    """ A shim to generate a client ID for IndieAuth/IndieLogin """
    from flask import request
    parsed = urllib.parse.urlparse(request.base_url)
    baseurl = '{}://{}'.format(parsed.scheme, parsed.hostname)
    LOGGER.debug("using client_id %s", baseurl)
    return baseurl
