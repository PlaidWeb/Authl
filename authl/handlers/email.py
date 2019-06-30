""" Handler for emailing a magic link """

import email
import re
import urllib.parse
import json

import validate_email
import ska

from . import Handler
from .. import disposition


DEFAULT_TEMPLATE_TEXT = """\
Hello! Someone asked to log in using this email address. If this
was you, please visit the following link within the next {minutes} minutes:

    {url}

If this wasn't you, you can safely disregard this message.

"""


class Email(Handler):
    """ Email via "magic link" """

    def __init__(self,
                 secret_key,
                 sendmail,
                 expires_time=900,
                 email_template_text=DEFAULT_TEMPLATE_TEXT):
        """ Instantiate a magic link email handler. Arguments:

        from_addr -- the address that the email should be sent from
        secret_key -- a secret key for the authentication algorithm to use.
            This should be a fixed value that is configured outside of code
            (e.g. via an environment variable)
        sendmail -- a function that, given an email.message object, sends it.
            It is the responsibility of this function to set the From and
            Subject headers before it sends.
        expires_time -- how long the email link should be valid for, in seconds
        email_template_text -- the plaintext template for the sent email,
            provided as a string.

        """
        self._sendmail = sendmail
        self._email_template_text = email_template_text
        self._lifetime = expires_time

        self._cfg = {
            'secret_key': secret_key,
            'signature_param': 's',
            'auth_user_param': 'u',
            'valid_until_param': 'v',
            'extra_param': 'e',
        }

    def service_name(self):
        return "Email"

    def url_scheme(self):
        return 'mailto:%', 'email@example.com'

    def handles_url(self, url):
        """ Validating email by regex: not even once """
        try:
            if urllib.parse.urlparse(url).scheme == 'mailto':
                return True
        except (ValueError, AttributeError):
            pass

        return validate_email.validate_email(url)

    def handles_page(self, headers, content):
        return False

    def initiate_auth(self, id_url, callback_url):
        # Extract the destination email from the identity URL
        dest_addr = urllib.parse.urlparse(id_url).path

        link_url = ska.sign_url(
            url=callback_url,
            auth_user=dest_addr,
            lifetime=self._lifetime,
            suffix='&' if '?' in callback_url else '?',
            **self._cfg)

        msg = email.message.EmailMessage()
        msg['To'] = dest_addr

        msg.set_content(self._email_template_text.format(
            url=link_url,
            minutes=self._lifetime / 60))

        self._sendmail(msg)

        return disposition.Notify("check yr email")

    def check_callback(self, url, get, data):
        validation = ska.validate_signed_request_data(
            data=get,
            **self._cfg)

        if validation.result:
            return disposition.Verified(get[self._cfg['auth_user_param']])

        return disposition.Error(','.join(validation.reason))
