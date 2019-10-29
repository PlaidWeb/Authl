""" Flask wrapper for Authl """

import json
import logging
import os
import typing
import urllib.parse

import flask
import werkzeug.exceptions as http_error
from rop import read_only_properties

from . import disposition, from_config, utils

LOGGER = logging.getLogger(__name__)


def setup(app: flask.Flask, config: typing.Dict[str, typing.Any], *args, **kwargs):
    """ Simple/legacy API for backwards compatibility. """
    return AuthlFlask(app, config, *args, **kwargs).instance


def set_cache(age: int) -> typing.Callable:
    """ Cache decorator to set the maximum cache age on a response """
    def decorator(func: typing.Callable) -> typing.Callable:
        def wrapped_func(*args, **kwargs):
            response = flask.make_response(func(*args, **kwargs))
            response.cache_control.max_age = age
            return response
        return wrapped_func
    return decorator


def load_template(filename: str) -> str:
    """ Load the built-in Flask template """
    return utils.read_file(os.path.join(os.path.dirname(__file__), 'flask_templates', filename))


def redir_dest_to_path(destination: str):
    """ Convert a redirection destination to a path fragment """
    if destination.startswith('/'):
        return destination[1:]
    return destination


def redir_path_to_dest(path: str):
    """ Convert a path fragment to a redirection destination """
    if path.startswith('/'):
        return path
    return '/' + path


@read_only_properties('login_name', 'callback_name', 'tester_name')
class AuthlFlask:
    """ Container that wraps an Authl instance for a Flask application """
    # pylint:disable=too-many-instance-attributes

    def __init__(self,
                 app: flask.Flask,
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
        :param str callback_name: The endpoint name for the callback handler,
            for flask.url_for()
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

        The login_render_func takes the following arguments; note that more may
        be added so it should also take a **kwargs for future compatibility:

            :param auth: the authl.Authl object
            :param login_url: the URL to use for the login form
            :param tester_url: the URL to use for the test callback
            :param redir: The redirection destination that the login URL will
                redirect them to

        If login_render_func returns a false value, the default login form will
        be used instead. This is useful for providing a conditional override, or
        as a rudimentary hook for analytics on the login flow or the like.

        The render_notify_func takes the following arguments:

            :param cdata: the client data for the handler

        The on_verified function receives the disposition.Verified object, and
        may return a Flask response of its own, ideally a flask.redirect(). This
        can be used to capture more information about the user (such as their
        display name) or to redirect certain users to an administrative screen
        of some sort.

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

        self.instance = from_config(config)

        self.login_name = login_name
        self.callback_name = callback_name
        self.tester_name = tester_name
        self._tester_path = tester_path
        self._login_render_func = login_render_func
        self._notify_render_func = notify_render_func
        self._session_auth_name = session_auth_name
        self.force_ssl = force_ssl
        if stylesheet:
            self.stylesheet = stylesheet
        self._on_verified = on_verified
        self.make_permanent = make_permanent

        for sfx in ['', '/', '/<path:redir>']:
            app.add_url_rule(login_path + sfx, login_name,
                             self._login_endpoint, methods=('GET', 'POST'))
        app.add_url_rule(callback_path + '/<hid>', callback_name, self._callback_endpoint)

        if tester_path:
            def find_service():
                from flask import request

                url = request.args.get('url')
                if not url:
                    return json.dumps(None)

                handler, _, canon_url = self.instance.get_handler_for_url(url)
                if handler:
                    return json.dumps({'name': handler.service_name,
                                       'url': canon_url})

                return json.dumps(None)
            app.add_url_rule(tester_path, tester_name, find_service)

    @property
    def url_scheme(self):
        """ Provide the _scheme parameter to be sent along to flask.url_for """
        return 'https' if self.force_ssl else None

    @set_cache(0)
    def _handle_disposition(self, disp: disposition.Disposition):
        if isinstance(disp, disposition.Redirect):
            # A simple redirection
            return flask.redirect(disp.url)

        if isinstance(disp, disposition.Verified):
            # The user is verified; log them in
            LOGGER.info("Successful login: %s", disp.identity)
            if self._session_auth_name is not None:
                flask.session.permanent = self.make_permanent
                flask.session[self._session_auth_name] = disp.identity

            if self._on_verified:
                response = self._on_verified(disp)
                if response:
                    return response

            return flask.redirect(disp.redir)

        if isinstance(disp, disposition.Notify):
            # The user needs to take some additional action
            return self._render_notify(disp.cdata)

        if isinstance(disp, disposition.Error):
            # The user's login failed
            flask.flash(disp.message)
            return self.render_login_form(destination=disp.redir)

        # unhandled disposition
        raise http_error.InternalServerError("Unknown disposition type " + type(disp))

    @set_cache(0)
    def _render_notify(self, cdata):
        if self._notify_render_func:
            result = self._notify_render_func(cdata)
            if result:
                return result

        return flask.render_template_string(load_template('notify.html'),
                                            cdata=cdata,
                                            stylesheet=self.stylesheet)

    def render_login_form(self, destination: str):
        """ Renders the login form, configured with the specified redirection path. """
        login_url = flask.url_for(self.login_name,
                                  redir=redir_dest_to_path(destination),
                                  _scheme=self.url_scheme,
                                  _external=self.force_ssl)
        test_url = self._tester_path and flask.url_for(self.tester_name,
                                                       _external=True)
        if self._login_render_func:
            result = self._login_render_func(login_url=login_url,
                                             test_url=test_url,
                                             auth=self.instance,
                                             redir=destination)
            if result:
                return result

        return flask.render_template_string(load_template('login.html'),
                                            login_url=login_url,
                                            test_url=test_url,
                                            stylesheet=self.stylesheet,
                                            auth=self.instance)

    def _login_endpoint(self, redir: str = ''):
        from flask import request

        if 'asset' in request.args:
            asset = request.args['asset']
            if asset == 'css':
                return load_template('authl.css'), {'Content-Type': 'text/css'}
            raise http_error.NotFound("Unknown asset " + asset)

        dest = redir_path_to_dest(redir)

        me_url = request.form.get('me', request.args.get('me'))
        if me_url:
            handler, hid, id_url = self.instance.get_handler_for_url(me_url)
            if handler:
                cb_url = flask.url_for(self.callback_name,
                                       hid=hid,
                                       _external=True,
                                       _scheme=self.url_scheme)
                return self._handle_disposition(handler.initiate_auth(
                    id_url,
                    cb_url,
                    dest))

            # No handler found, so flash an error message to login_form
            flask.flash('Unknown authorization method')

        return self.render_login_form(destination=dest)

    def _callback_endpoint(self, hid: str):
        from flask import request

        handler = self.instance.get_handler_by_id(hid)
        return self._handle_disposition(
            handler.check_callback(request.url, request.args, request.form))

    @property
    def stylesheet(self) -> str:
        """ Gets the stylesheet for the Flask templates """
        return flask.url_for(self.login_name, asset='css')


def client_id():
    """ A shim to generate a client ID for IndieAuth/IndieLogin """
    from flask import request
    parsed = urllib.parse.urlparse(request.base_url)
    baseurl = '{}://{}'.format(parsed.scheme, parsed.hostname)
    LOGGER.debug("using client_id %s", baseurl)
    return baseurl
