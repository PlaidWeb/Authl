"""
Flask wrapper
=============

:py:class:`AuthlFlask` is an easy-to-use wrapper for use with `Flask`_ . By
default it gives you a login form (with optional URL tester) and a login
endpoint that stores the verified identity in ``flask.session['me']``. All this
behavior is configurable.

.. _Flask: https://flask.palletsprojects.com/

The basic usage is very simple:

.. code-block:: python

    import flask
    import authl.flask

    app = flask.Flask(__name__)
    app.secret_key = "extremely secret"

    authl.flask.setup(app, {
        # Simple IndieAuth setup
        'INDIEAUTH_CLIENT_ID': authl.flask.client_id,

        # Minimal Fediverse setup
        'FEDIVERSE_NAME': 'My website',

        # Send email using localhost
        'EMAIL_FROM': 'me@example.com',
        'SMTP_HOST': 'localhost',
        'SMTP_PORT': 25
    }, tester_path='/test')

    @app.route('/')
        if 'me' in flask.session:
            return 'Hello {me}. Want to <a href="{logout}">log out</a>?'.format(
                me=flask.session['me'], logout=flask.url_for(
                    'logout', redir=flask.request.path[1:])
            )

        return 'You are not logged in. Want to <a href="{login}">log in</a>?'.format(
            login=flask.url_for('authl.login', redir=flask.request.path[1:]))

    @app.route('/logout')
    def logout():
        flask.session.clear()
        return flask.redirect('/')

This gives you a very simple login form configured to work with IndieAuth,
Fediverse, and email at the default location of ``/login``, and a logout
mechanism at ``/logout``. The endpoint at ``/test`` can be used to test an
identity URL for login support.

"""

import json
import logging
import os
import typing
import urllib.parse
from typing import Optional

import flask
import werkzeug.exceptions as http_error

from . import Authl, disposition, from_config, tokens, utils

LOGGER = logging.getLogger(__name__)


def setup(app: flask.Flask, config: typing.Dict[str, typing.Any], **kwargs) -> Authl:
    """ Simple setup function.

    :param flask.flask app: The Flask app to configure with Authl.

    :param dict config: Configuration values for the Authl instance; see
        :py:func:`authl.from_config`

    :param kwargs: Additional arguments to pass along to the
        :py:class:`AuthlFlask` constructor

    :returns: The configured :py:class:`authl.Authl` instance. Note that if you
        want the :py:class:`AuthlFlask` instance you should instantiate that directly.

    """
    return AuthlFlask(app, config, **kwargs).authl


def load_template(filename: str) -> str:
    """ Load the built-in Flask template.

    :param str filename: The filename of the built-in template

    Raises `FileNotFoundError` on no such template

    :returns: the contents of the template.
    """
    return utils.read_file(os.path.join(os.path.dirname(__file__), 'flask_templates', filename))


def _nocache() -> typing.Callable:
    """ Cache decorator to set the maximum cache age on a response """
    def decorator(func: typing.Callable) -> typing.Callable:
        def wrapped_func(*args, **kwargs):
            response = flask.make_response(func(*args, **kwargs))
            response.cache_control.max_age = 0
            return response
        return wrapped_func
    return decorator


def _redir_dest_to_path(destination: str):
    """ Convert a redirection destination to a path fragment """
    assert destination.startswith('/'), "Redirection destinations must begin with '/'"
    return destination[1:]


def _redir_path_to_dest(path: str):
    """ Convert a path fragment to a redirection destination """
    assert not path.startswith('/'), "Path fragments cannot start with '/'"
    return '/' + path


class AuthlFlask:
    """ Easy Authl wrapper for use with a Flask application.

    :param flask.Flask app: the application to attach to

    :param dict config: Configuration directives for Authl's handlers. See
        from_config for more information.

    :param str login_name: The endpoint name for the login handler, for
        flask.url_for()

    :param str login_path: The mount point of the login endpoint

        The login endpoint takes the following arguments (as specified via
        :py:func:`flask.url_for`):

            * ``me``: The URL to initiate authentication for
            * ``redir``: Where to redirect the user to after successful login


    :param str callback_name: The endpoint name for the callback handler,
        for flask.url_for()

    :param str callback_path: The mount point of the callback handler endpoints.
        For example, if this is set to ``/login_cb`` then your actual handler
        callbacks will be at ``/login_cb/{cb_id}`` for the handler's ``cb_id``
        property; for example, the :py:class:`authl.handlers.email_addr.EmailAddress`
        handler's callback will be mounted at ``/login_cb/e``.

    :param str tester_name: The endpoint name for the URL tester, for
        flask.url_for()

    :param str tester_path: The mount point of the URL tester endpoint

        The URL tester endpoint takes a query parameter of ``url`` which is the
        URL to check. It returns a JSON object that describes the detected
        handler (if any), with the following attributes:

            * ``name``: the service name
            * ``url``: a canonicized version of the URL

        The URL tester endpoint will only be mounted if ``tester_path`` is
        specified. This will also enable a small asynchronous preview in the default
        login form.

    :param function login_render_func: The function to call to render the login
        page; if not specified a default will be provided.

        This function takes the following arguments; note that more may
        be added so it should also take a ``**kwargs`` for future compatibility:

        * ``auth``: the :py:class:`authl.Authl` object

        * ``login_url``: the URL to use for the login form

        * ``tester_url``: the URL to use for the test callback

        * ``redir``: The redirection destination that the login URL will
            redirect them to

        * ``id_url``: Any pre-filled value for the ID url

        * ``error``: Any error message that occurred

        If ``login_render_func`` returns a falsy value, the default login form
        will be used instead. This is useful for providing a conditional
        override, or as a rudimentary hook for analytics on the login flow or
        the like.

    :param function notify_render_func: The function to call to render the user
        notification page; if not specified a default will be provided.

        This function takes the following arguments:

            * ``cdata``: the client data for the handler

    :param function post_form_render_func: The function to call to render a
        necessary post-login form; if not specified a default will be provided.

        This function takes the following arguments:

            * ``message``: the notification message for the user
            * ``data``: the data to pass along in the POST request
            * ``url``: the URL to send the POST request to

    :param str session_auth_name: The session parameter to use for the
        authenticated user. Set to None if you want to use your own session
        management.

    :param bool force_https: Whether to force authentication to switch to a
        ``https://`` connection

    :param str stylesheet: the URL to use for the default page stylesheet; if
        not

    :param function on_verified: A function to call on successful login (called
        after setting the session value)

        This function receives the :py:class:`authl.disposition.Verified` object, and
        may return a Flask response of its own, which should ideally be a
        ``flask.redirect()``. This can be used to capture more information about
        the user (such as filling out a user profile) or to redirect certain
        users to an administrative screen of some sort.

    :param bool make_permanent: Whether a session should persist past the
        browser window closing

    :param tokens.TokenStore token_storage: Storage for token data for
        methods which use it. Uses the same default as :py:func:`authl.from_config`.

        Note that if the default is used, the ``app.secret_key`` **MUST** be set
        before this class is initialized.

    :param state_storage: The mechanism to use for transactional state
        storage for login methods that need it. Defaults to using the Flask
        user session.

    :param session_namespace: A namespace for Authl to keep a small amount of
        user session data in. Should never need to be changed.

    """
    # pylint:disable=too-many-instance-attributes

    def __init__(self,
                 app: flask.Flask,
                 config: typing.Dict[str, typing.Any],
                 login_name: str = 'authl.login',
                 login_path: str = '/login',
                 callback_name: str = 'authl.callback',
                 callback_path: str = '/cb',
                 tester_name: str = 'authl.test',
                 tester_path: Optional[str] = None,
                 login_render_func: Optional[typing.Callable] = None,
                 notify_render_func: Optional[typing.Callable] = None,
                 post_form_render_func: Optional[typing.Callable] = None,
                 session_auth_name: typing.Optional[str] = 'me',
                 force_https: bool = False,
                 stylesheet: Optional[typing.Union[str, typing.Callable]] = None,
                 on_verified: Optional[typing.Callable] = None,
                 make_permanent: bool = True,
                 state_storage: Optional[typing.Dict] = None,
                 token_storage: Optional[tokens.TokenStore] = None,
                 session_namespace='_authl',
                 ):
        # pylint:disable=too-many-arguments,too-many-locals,too-many-statements

        if state_storage is None:
            state_storage = typing.cast(typing.Dict, flask.session)

        self.authl = from_config(
            config,
            state_storage,
            token_storage)

        self._session = state_storage
        self.login_name = login_name
        self.callback_name = callback_name
        self.tester_name = tester_name
        self._tester_path = tester_path
        self._login_render_func = login_render_func
        self._notify_render_func = notify_render_func
        self._post_form_render_func = post_form_render_func
        self._session_auth_name = session_auth_name
        self.force_https = force_https
        self._stylesheet = stylesheet
        self._on_verified = on_verified
        self.make_permanent = make_permanent
        self._prefill_key = session_namespace + '.prefill'

        for sfx in ['', '/', '/<path:redir>']:
            app.add_url_rule(login_path + sfx, login_name,
                             self._login_endpoint, methods=('GET', 'POST'))
        app.add_url_rule(callback_path + '/<hid>',
                         callback_name,
                         self._callback_endpoint,
                         methods=('GET', 'POST'))

        if tester_path:
            def find_service():
                from flask import request

                url = request.args.get('url')
                if not url:
                    return json.dumps(None)

                handler, _, canon_url = self.authl.get_handler_for_url(url)
                if handler:
                    return json.dumps({'name': handler.service_name,
                                       'url': canon_url})

                return json.dumps(None)
            app.add_url_rule(tester_path, tester_name, find_service)

    @property
    def url_scheme(self):
        """ Provide the _scheme parameter to be sent along to flask.url_for """
        return 'https' if self.force_https else None

    @_nocache()
    def _handle_disposition(self, disp: disposition.Disposition):
        if isinstance(disp, disposition.Redirect):
            # A simple redirection
            return flask.redirect(disp.url)

        if isinstance(disp, disposition.Verified):
            # The user is verified; log them in
            self._session.pop(self._prefill_key, None)

            LOGGER.info("Successful login: %s", disp.identity)
            if self._session_auth_name is not None:
                flask.session.permanent = self.make_permanent  # pylint:disable=assigning-non-slot
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
            return self.render_login_form(destination=disp.redir, error=disp.message)

        if isinstance(disp, disposition.NeedsPost):
            # A POST request is required to proceed
            return self._render_post_form(url=disp.url, message=disp.message, data=disp.data)

        # unhandled disposition
        raise http_error.InternalServerError(f"Unknown disposition type {str(type(disp))}")

    @_nocache()
    def _render_notify(self, cdata):
        if self._notify_render_func:
            result = self._notify_render_func(cdata=cdata)
            if result:
                return result

        return flask.render_template_string(load_template('notify.html'),
                                            cdata=cdata,
                                            stylesheet=self.stylesheet)

    @_nocache()
    def _render_post_form(self, url, message, data):
        if self._post_form_render_func:
            result = self._post_form_render_func(url=url, message=message, data=data)
            if result:
                return result

        return flask.render_template_string(load_template('post-needed.html'),
                                            url=url,
                                            message=message,
                                            data=data,
                                            stylesheet=self.stylesheet)

    def render_login_form(self, destination: str, error: typing.Optional[str] = None):
        """
        Renders the login form. This might be called by the Flask app if, for
        example, a page requires login to be seen.

        :param str destination: The redirection destination, as a full path
            (e.g. ``'/path/to/view'``)

        :param str error: Any error message to display on the login form
        """
        login_url = flask.url_for(self.login_name,
                                  redir=_redir_dest_to_path(destination or '/'),
                                  _scheme=self.url_scheme,
                                  _external=self.force_https)
        test_url = self._tester_path and flask.url_for(self.tester_name,
                                                       _external=True)
        id_url = self._session.get(self._prefill_key, '')
        LOGGER.debug('id_url: %s', id_url)

        render_args: typing.Dict[str, typing.Any] = {
            'login_url': login_url,
            'test_url': test_url,
            'auth': self.authl,
            'id_url': id_url,
            'error': error,
            'redir': destination,
        }

        if self._login_render_func:
            result = self._login_render_func(**render_args)
            if result:
                return result

        return flask.render_template_string(load_template('login.html'),
                                            stylesheet=self.stylesheet,
                                            **render_args)

    def _login_endpoint(self, redir: str = ''):
        from flask import request

        if 'asset' in request.args:
            asset = request.args['asset']
            if asset == 'css':
                return load_template('authl.css'), {'Content-Type': 'text/css'}
            raise http_error.NotFound("Unknown asset " + asset)

        dest = _redir_path_to_dest(redir)
        error = None

        me_url = request.form.get('me', request.args.get('me'))
        if me_url:
            # Process the login request
            self._session[self._prefill_key] = me_url
            handler, hid, id_url = self.authl.get_handler_for_url(me_url)
            if handler:
                cb_url = flask.url_for(self.callback_name,
                                       hid=hid,
                                       _external=True,
                                       _scheme=self.url_scheme)
                return self._handle_disposition(handler.initiate_auth(
                    id_url,
                    cb_url,
                    dest))

            # No handler found, so provide error message to login_form
            error = 'Unknown authentication method'

        return self.render_login_form(destination=dest, error=error)

    def _callback_endpoint(self, hid: str):
        from flask import request

        handler = self.authl.get_handler_by_id(hid)
        if not handler:
            return self._handle_disposition(disposition.Error("Invalid handler", ''))
        return self._handle_disposition(
            handler.check_callback(request.base_url, request.args, request.form))

    @ property
    def stylesheet(self) -> str:
        """ The stylesheet to use for the Flask templates """
        if self._stylesheet:
            return utils.resolve_value(self._stylesheet)
        return flask.url_for(self.login_name, asset='css')


def client_id():
    """ A shim to generate a client ID based on the current site URL, for use
    with IndieAuth, Fediverse, and so on. """
    from flask import request
    parsed = urllib.parse.urlparse(request.base_url)
    baseurl = f'{parsed.scheme}://{parsed.hostname}'
    LOGGER.debug("using client_id %s", baseurl)
    return baseurl
