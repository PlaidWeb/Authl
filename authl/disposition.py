"""
Dispositions
============

A :py:class:`Disposition` represents the result of a phase of an authentication
transaction, and tells the top-level application what to do next.

"""
# pylint:disable=too-few-public-methods


from abc import ABC
from typing import Optional


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
        return f'REDIR:{self.url}'


class Verified(Disposition):
    """
    Indicates that the user is now verified; it is now up to
    the application to add that authorization to the user session and redirect the
    client to the actual view.

    :param str identity: The verified identity URL
    :param str redir: Where to redirect the user to
    :param dict profile: The user's profile information. Standardized keys:

        * ``avatar``: A URL to the user's avatar image
        * ``bio``: Brief biographical information
        * ``homepage``: The user's personal homepage
        * ``location``: The user's stated location
        * ``name``: The user's display/familiar name
        * ``pronouns``: The user's declared pronouns
        * ``profile_url``: A human-readable URL to link to the user's
          service-specific profile (which may or may not be the same as their
          identity URL).
        * ``endpoints``: A dictionary of key-value pairs referring to the user's
          various integration services

    """

    def __init__(self, identity: str, redir: str, profile: Optional[dict] = None):
        self.identity = identity
        self.redir = redir
        self.profile = profile or {}

    def __str__(self):
        return f'VERIFIED:{self.identity}'


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
        return f'NOTIFY:{str(self.cdata)}'


class Error(Disposition):
    """
    Indicates that authorization failed.

    :param str message: The error message to display
    :param str redir: The original redirection target of the auth attempt, if
        available
    """

    def __init__(self, message, redir: str):
        self.message = str(message)
        self.redir = redir

    def __str__(self):
        return f'ERROR:{self.message}'


class NeedsPost(Disposition):
    """
    Indicates that the callback needs to be re-triggered as a POST request.

    :param str url: The URL that needs to be POSTed to
    :param str message: A user-friendly message to display
    :param dict data: POST data to be sent in the request, as key-value pairs
    """

    def __init__(self, url: str, message, data: dict):
        self.url = url
        self.message = str(message)
        self.data = data

    def __str__(self):
        return f'NEEDS-POST:{self.message}'
