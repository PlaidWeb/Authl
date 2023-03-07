Authl
=====

Authl is an authentication library that simplifies adding user authentication to
your Python application. In particular, it allows the easy use of common
third-party identity services such as Twitter, Fediverse, and IndieWeb
implementations, as well as supporting signin via emailed "magic links." It also
provides an extension API such that you can provide your own identity providers
as appropriate.

Installation
------------

Authl requires Python 3.8.1 or later.

Install with pip::

    pip install Authl

Or, if you would like to work from the latest source::

    git clone https://github.com/PlaidWeb/Authl.git

Authl uses `Poetry <https://python-poetry.org/>`_ and ``make`` for its build and
dependency management.

Further reading
---------------

.. toctree::
    authl
    handlers
    flow
    flask
