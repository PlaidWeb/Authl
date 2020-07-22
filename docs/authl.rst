API Documentation
=================

This is a brief overview about how to do it which will be framework-agnostic. If you want to use Authl with `Flask`_, instead consider using the :py:mod:`authl.flask` wrapper.

.. _Flask: https://flask.palletsprojects.com/

Typically you will simply use :py:func:`authl.from_config` to build an instance with your configured handlers. However, you can also instance it and your handlers directly. See the documentation for :py:class:`Authl` and :py:func:`Authl.add_handler`, as well as the documentation for :py:mod:`authl.handlers`.

For the login flow, you need two parts: a login form, and a callback handler. The login form, at its simplest, should call :py:func:`Authl.get_handler_for_url` with the user's login URL to get the appropriate handler, and then call the handler's :py:func:`handlers.Handler.initiate_auth` function. The ``callback_uri`` argument needs to be able to map back to the handler in some way; typically you will include the handler's ``cb_id`` in the URL, either as a query parameter or as a path component. ``get_handler_for_url`` will then return a :py:class:`disposition.Disposition` object which should then direct the client in some way. Typically this will be either a :py:class:`disposition.Redirect` or a :py:class:`disposition.Notify`, but any of the disposition types are possible.

The callback then must look up the associated handler and pass the request URL, the parsed ``GET`` arguments (if any), and the parsed ``POST`` arguments (if any) to the handler's :py:func:`handlers.Handler.check_callback` method. The resulting :py:class:`disposition.Disposition` object then indicates what comes next. Typically this will be either a :py:class:`disposition.Error` or a :py:class:`disposition.Verified`, but again, any disposition type is possible and must be handled accordingly.

.. automodule:: authl
   :members:

.. automodule:: authl.disposition
    :members:

.. automodule:: authl.tokens
    :members:
    :member-order: bysource

