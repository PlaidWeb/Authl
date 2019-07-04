""" Authentication response dispositions """
# pylint:disable=too-few-public-methods


class Disposition:
    """ Base class for all response dispositions """


class Redirect(Disposition):
    """ A disposition that indicates that the request should redirect to another
    URL """

    def __init__(self, url):
        self.url = url


class Verified(Disposition):
    """ A disposition that indicates that the user is verified; it is now up to
    the web app to add that authorization to the user session and redirect the
    client to the actual view

    Profile will just be a MultiDict with whatever other junk the provider
    includes in the profile, which is probably useful for some use case
    """

    def __init__(self, identity, profile=None):
        self.identity = identity
        self.profile = profile or {}


class Notify(Disposition):
    """ A disposition that indicates that a notification should be sent to the
    user (e.g. "check your email").

    For localization/generality purposes this will probably be configured in the
    handler by the web app.
    """

    def __init__(self, cdata, args=None):
        self.cdata = cdata
        self.args = args or {}


class Error(Disposition):
    """ A disposition that indicates that authorization failed, hopefully with
    an informative message. """

    def __init__(self, message):
        self.message = message
