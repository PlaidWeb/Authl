""" Flask wrapper for Authl """

import json
import logging
import os
import typing
import urllib.parse

import flask
import werkzeug.exceptions as http_error

from . import disposition, from_config, utils

LOGGER = logging.getLogger(__name__)


def setup(app: flask.Flask,
          config: typing.Dict[str, typing.Any],
          login_name: str = 'authl.login',
          login_path: str = '/login',
          callback_name: str = 'authl.callback',
          callback_path: str = '/cb',
          tester_name: str = 'authl.test',
          tester_path: str = None,
          login_render_func: typing.Callable = None,
          notify_render_func: typing.Callable = None,
          session_auth_name: str = 'me',
          force_ssl: bool = False,
          stylesheet: str = None,
          on_verified: typing.Callable = None,
          make_permanent: bool = True
          ):
    """ Setup Authl to work with a Flask application.

    The Flask application should be configured with a secret_key before this
    function is called.

    :param flask.Flask app: the application to attach to
    :param dict config: Configuration directives for Authl's handlers. See
        from_config for more information.
    :param str login_name: The endpoint name for the login handler, for
        flask.url_for()
    :param str login_path: The mount point of the login route
    :param str callback_name: The endpoint name for the callback handler, for
        flask.url_for()
    :param str callback_path: The mount point of the callback handler
    :param str tester_name: The endpoint name for the URL tester, for
        flask.url_for()
    :param str tester_path: The mount point of the URL tester
    :param function login_render_func: The function to call to render the login
        page; if not specified a default will be provided.
    :param function notify_render_func: The function to call to render the user
        notification page; if not specified a default will be provided.
    :param str session_auth_name: The session parameter to use for the
        authenticated user. Set to None if you want to use your own session
        management.
    :param bool force_ssl: Whether to force authentication to switch to an SSL
        connection
    :param str stylesheet: the URL to use for the default page stylesheet; if
        not
    :param function on_verified: A function to call on successful login (called
        after setting the session value)
    :param bool make_permanent: Whether a session should persist past the
        browser window closing

    The login_render_func takes the following arguments:

        :param login_url: the URL to use for the login form
        :param auth: the Authl object

    If login_render_func returns a false value, the default login form will be
    used instead. This is useful for providing a conditional override, or as a
    rudimentary hook for analytics on the login flow or the like.

    The render_notify_func takes the following arguments:

        :param cdata: the client data for the handler

    The on_verified function receives the disposition.Verified object, and may
    return a Flask response of its own, ideally a flask.redirect(). This can be
    used to capture more information about the user (such as their display name)
    or to redirect certain users to an administrative screen of some sort.

    The login endpoint takes a query parameter of 'me' which is the URL to
    authenticate against.

    The URL tester endpoint takes a query parameter of 'url' which is the URL
    to check. It returns a JSON object that describes the detected handler, with
    the following attributes:

        :param name: the service name
        :param url: a canonicized version of the URL

    The URL tester endpoint will only be mounted if tester_path is specified.
    This will also enable a small asynchronous preview in the default login form.

    Return value: the configured Authl instance

    """
    # pylint:disable=too-many-arguments,too-many-locals,too-many-statements

    instance = from_config(config)
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
    def handle_disposition(disp: disposition.Disposition, redir: str):
        if isinstance(disp, disposition.Redirect):
            # A simple redirection
            return flask.redirect(disp.url)

        if isinstance(disp, disposition.Verified):
            # The user is verified; log them in
            LOGGER.info("Successful login: %s", disp.identity)
            if session_auth_name is not None:
                flask.session.permanent = make_permanent
                flask.session[session_auth_name] = disp.identity

            if on_verified:
                response = on_verified(disp)
                if response:
                    return response

            return flask.redirect('/' + disp.redir)

        if isinstance(disp, disposition.Notify):
            # The user needs to take some additional action
            return render_notify(disp.cdata)

        if isinstance(disp, disposition.Error):
            # The user's login failed
            flask.flash(disp.message)
            return render_login_form(redir=redir)

        # unhandled disposition
        raise http_error.InternalServerError("Unknown disposition type " + type(disp))

    def load_template(filename: str) -> str:
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

    def render_login_form(redir: str):
        login_url = flask.url_for(login_name,
                                  redir=redir,
                                  _scheme=url_scheme,
                                  _external=bool(url_scheme))
        test_url = tester_path and flask.url_for(tester_name,
                                                 _external=True,
                                                 _scheme=url_scheme)
        if login_render_func:
            result = login_render_func(login_url=login_url,
                                       test_url=test_url,
                                       auth=instance)
            if result:
                return result

        return flask.render_template_string(load_template('login.html'),
                                            login_url=login_url,
                                            test_url=test_url,
                                            stylesheet=get_stylesheet(),
                                            auth=instance)

    def login(redir: str = ''):
        from flask import request

        if 'asset' in request.args:
            asset = request.args['asset']
            if asset == 'css':
                return load_template('authl.css'), {'Content-Type': 'text/css'}
            raise http_error.NotFound("Unknown asset " + asset)

        me_url = request.form.get('me', request.args.get('me'))
        if me_url:
            handler, hid, id_url = instance.get_handler_for_url(me_url)
            if handler:
                cb_url = flask.url_for(callback_name,
                                       hid=hid,
                                       _external=True,
                                       _scheme=url_scheme)
                return handle_disposition(handler.initiate_auth(id_url,
                                                                cb_url,
                                                                redir), redir)

            # No handler found, so flash an error message to login_form
            flask.flash('Unknown authorization method')

        return render_login_form(redir=redir)

    for sfx in ['', '/', '/<path:redir>']:
        app.add_url_rule(login_path + sfx, login_name, login, methods=('GET', 'POST'))

    def callback(hid: str, redir: str = ''):
        from flask import request

        handler = instance.get_handler_by_id(hid)
        return handle_disposition(
            handler.check_callback(request.url, request.args, request.form), redir
        )
    app.add_url_rule(callback_path + '/<hid>', callback_name, callback)

    def get_stylesheet() -> str:
        if stylesheet is None:
            return flask.url_for(login_name, asset='css')
        return stylesheet

    if tester_path:
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
        app.add_url_rule(tester_path, tester_name, find_service)

    return instance


def client_id():
    """ A shim to generate a client ID for IndieAuth/IndieLogin """
    from flask import request
    parsed = urllib.parse.urlparse(request.base_url)
    baseurl = '{}://{}'.format(parsed.scheme, parsed.hostname)
    LOGGER.debug("using client_id %s", baseurl)
    return baseurl
