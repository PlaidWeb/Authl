Authentication Flow
===================

This is a brief, framework-agnostic overview of how to use Authl. If you want to
use Authl with `Flask`_, instead consider using the :py:mod:`authl.flask`
wrapper.

.. _Flask: https://flask.palletsprojects.com/

Notably, the example code below is not written against any specific framework
and is just to be used as a rough example of how it might look.

Typically you will simply use :py:func:`authl.from_config` to build an instance
with your configured handlers. However, you can also instance it and your
handlers directly. See the documentation for :py:class:`Authl` and
:py:func:`Authl.add_handler`, as well as the documentation for
:py:mod:`authl.handlers`.

For the login flow, you need two parts: a login form, and a callback handler.

The login form should, at the very least, have a text input field for users to
enter their identity URL, and should track the final post-login redirection
target.

When the form is submitted, it calls
:py:func:`Authl.get_handler_for_url` with the user's login URL to get the
appropriate handler, and then call the handler's
:py:func:`handlers.Handler.initiate_auth` function. The ``callback_uri``
argument needs to be able to map back to the handler in some way; typically you
will include the handler's ``cb_id`` in the URL, either as a query parameter or
as a path component. ``get_handler_for_url`` will then return a
:py:class:`disposition.Disposition` object which should then direct the client
in some way. Typically this will be either a :py:class:`disposition.Redirect` or
a :py:class:`disposition.Notify`, but any of the disposition types are possible.

The callback then must look up the associated handler and pass the request URL,
the parsed ``GET`` arguments (if any), and the parsed ``POST`` arguments (if
any) to the handler's :py:func:`handlers.Handler.check_callback` method. The
resulting :py:class:`disposition.Disposition` object then indicates what comes
next. Typically this will be either a :py:class:`disposition.Error` or a
:py:class:`disposition.Verified`, but again, any disposition type is possible
and must be handled accordingly.

Example (pseudo-)code follows:

.. code-block:: python

    def handle_disposition(disp):
        if isinstance(disp, disposition.Redirect):
            return redirect(disp.url)
        if isinstance(disp, disposition.Verified):
            set_user_session(username=disp.identity)
            return redirect(disp.redir)
        if isinstance(disp, disposition.Notify):
            return render_notification_page(message=disp.cdata)
        if isinstance(disp, disposition.NeedsPost):
            return render_post_form(message=disp.message, url=disp.url, data=disp.data)
        if isinstance(disp, disposition.Error):
            return render_login_form(error=disp.message, redir=disp.redir)
        raise RuntimeError("Unknown disposition type " + disp)

    def handle_login_form(request):
        # The login form should have some means of providing the post-login
        # redirection URL
        redir_url = get_redir_url(request)

        # Get the submitted user identity; it's a good idea to support both
        # GET and POST arguments for this to let people bookmark a quick
        # login URL if they so desire
        me_url = request.args.get('me', request.post.get('me'))
        if me_url:
            handler, hid, id_url = authl_instance.get_handler_for_url(me_url)
            if handler:
                # get_callback_url is implemented by the app, and produces a URL
                # that can map to a handler by handler ID
                cb_url = get_callback_url(hid)

                # handle_disposition is implemented by the app, and handles the
                # result of an authentication step
                return handle_disposition(
                    handler.initiate_auth(id_url, cb_url, redir_url))

        return render_login_form(
            error="Unknown authentication method" if me_url else None,
            redir=redir_url)

    def handle_callback(request):
        hid = get_hid_from_url(request.url)
        handler = authl_instance.get_handler_by_id(hid)
        if not handler:
            return render_login_page(error="Invalid callback")
        return handle_disposition(handler.check_callback(request.url,
                                                         request.args,
                                                         request.post))

Login form UX
-------------

Authl handlers also provide a few mechanisms that allow for an improved user
experience; for example, :py:func:`authl.handlers.Handler.service_name` and
:py:func:`authl.handlers.Handler.url_schemes` can be used to build out form
elements that provide more information about which handlers are available, and
:py:func:`authl.Authl.get_handler_for_url` can be used to implement an
interactive "URL tester" to tell users in real-time whether the URL they're
entering is a valid identity. This functionality is all expressed in the
:py:mod:`authl.flask` implementation and should absolutely be replicated in any
other frontend implementation.

See the `default Flask login template
<https://github.com/PlaidWeb/Authl/blob/main/authl/flask_templates/login.html>`_
for an example of how this might look.

Asynchronous operation
----------------------

Note that many of the underlying libraries that Authl uses are blocking, so as a
result, Authl as a whole will be blocking for the foreseeable future. However,
if you want to use Authl asynchronously, you can wrap the functions using
:py:func:`asyncio.loop.run_in_executor` or using a higher-level library such as
`a_sync <https://github.com/notion/a_sync>`_ to manage this for you.

The functions you'll specifically want to wrap are:

* :py:func:`authl.Authl.get_handler_for_url`
* :py:func:`authl.handlers.Handler.initiate_auth` (for the returned handler)
* :py:func:`authl.handlers.Handler.check_callback` (for the returned handler)

For example, an async version of the above flow might look like:

.. code-block:: python

    import asyncio

    async def handle_login_form(request):
        loop = asyncio.get_running_loop()

        redir_url = get_redir_url(request)
        me_url = request.args.get('me', request.post.get('me'))
        if me_url:
            handler, hid, id_url = await loop.run_in_executor(
                None,
                authl_instance.get_handler_for_url, me_url)
            if handler:
                bc_url = get_callback_url(hid)
                return handle_disposition(await loop.run_in_executor(
                    None, handler.initiate_auth,
                    id_url, cb_url, redir_url))

        return render_login_form(redir=redir_url)

    async def handle_callback(request):
        loop = asyncio.get_running_loop()

        hid = get_hid_from_url(request.url)
        handler = authl_instance.get_handler_by_id(hid)
        if not handler:
            return render_login_page(error="Invalid callback")

        return handle_disposition(await loop.run_in_executor(
            None, handler.check_callback,
            request.url, request.args, request.post))
