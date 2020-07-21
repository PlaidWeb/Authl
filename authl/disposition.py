"""
Dispositions
============

A :py:class:`Disposition` represents the result of a phase of an authentication
transaction, and tells the top-level application what to do next.

"""
# pylint:disable=too-few-public-methods


from abc import ABC


class Disposition(ABC):
    """ Base class for all response dispositions. """
    # pylint:disable=too-few-public-methods


class Redirect(Disposition):
    """ Indicates that the authenticating user should be redirected to another
    URL for the next step.

    :param str url: The URL to redirect the user to

    """

    def __init__(self, url: str):
        self.url = url

    def __str__(self):
        return 'REDIR:' + self.url


class Verified(Disposition):
    """
    Indicates that the user is now verified; it is now up to
    the application to add that authorization to the user session and redirect the
    client to the actual view.

    :param str identity: The verified identity URL
    :param str redir: Where to redirect the user to
    :param dict profile: The user's profile information

    """

    def __init__(self, identity, redir, profile=None):
        self.identity = identity
        self.redir = redir
        self.profile = profile or {}

    def __str__(self):
        return 'VERIFIED:' + self.identity


class Notify(Disposition):
    """
    Indicates that a notification should be sent to the user to take an external
    action, such as checking email or waiting for a text message or the like.

    The actual notification client data is to be configured in the underlying
    handler by the application, and will typically be a string.

    :param cdata: Notification client data
    """

    def __init__(self, cdata):
        self.cdata = cdata

    def __str__(self):
        return 'NOTIFY:' + str(self.cdata)


class Error(Disposition):
    """
    Indicates that authorization failed.

    :param str message: The error message to display
    :param str redir: The original redirection target of the auth attempt, if
        available
    """

    def __init__(self, message, redir: str):
        self.message = message
        self.redir = redir

    def __str__(self):
        return 'ERROR:' + self.message
