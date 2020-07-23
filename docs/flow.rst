Authentication Flow
===================

This is a brief, framework-agnostic overview of how to use Authl. If you want to use Authl with `Flask`_, instead consider using the :py:mod:`authl.flask` wrapper.

.. _Flask: https://flask.palletsprojects.com/

Typically you will simply use :py:func:`authl.from_config` to build an instance with your configured handlers. However, you can also instance it and your handlers directly. See the documentation for :py:class:`Authl` and :py:func:`Authl.add_handler`, as well as the documentation for :py:mod:`authl.handlers`.

For the login flow, you need two parts: a login form, and a callback handler. The login form, at its simplest, should call :py:func:`Authl.get_handler_for_url` with the user's login URL to get the appropriate handler, and then call the handler's :py:func:`handlers.Handler.initiate_auth` function. The ``callback_uri`` argument needs to be able to map back to the handler in some way; typically you will include the handler's ``cb_id`` in the URL, either as a query parameter or as a path component. ``get_handler_for_url`` will then return a :py:class:`disposition.Disposition` object which should then direct the client in some way. Typically this will be either a :py:class:`disposition.Redirect` or a :py:class:`disposition.Notify`, but any of the disposition types are possible.

The callback then must look up the associated handler and pass the request URL, the parsed ``GET`` arguments (if any), and the parsed ``POST`` arguments (if any) to the handler's :py:func:`handlers.Handler.check_callback` method. The resulting :py:class:`disposition.Disposition` object then indicates what comes next. Typically this will be either a :py:class:`disposition.Error` or a :py:class:`disposition.Verified`, but again, any disposition type is possible and must be handled accordingly.

Authl handlers also provide a few mechanisms that allow for an improved user experience; for example, :py:func:`authl.handlers.Handler.service_name` and :py:func:`authl.handlers.Handler.url_schemes` can be used to build out form elements that provide more information about which handlers are available, and :py:func:`authl.Authl.get_handler_for_url` can be used to implement an interactive "URL tester" to tell users in real-time whether the URL they're entering is a valid identity. This functionality is all expressed in the :py:mod:`authl.flask` implementation and should absolutely be replicated in any other frontend implementation.
