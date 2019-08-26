""" Handler for emailing a magic link """

import email
import html
import logging
import math
import time
import urllib.parse

import expiringdict
import validate_email

from .. import disposition, utils
from . import Handler

LOGGER = logging.getLogger(__name__)

DEFAULT_TEMPLATE_TEXT = """\
Hello! Someone, possibly you, asked to log in using this email address. If this
was you, please visit the following link within the next {minutes} minutes:

    {url}

If this wasn't you, you can safely disregard this message.

"""

DEFAULT_WAIT_ERROR = """An email has already been sent to {email}. Please be
patient; you may try again in {minutes} minutes."""


class EmailAddress(Handler):
    """ Email via "magic link" """

    @property
    def service_name(self):
        return 'Email'

    @property
    def url_schemes(self):
        return [('mailto:%', 'email@example.com'),
                ('%', 'email@example.com')]

    @property
    def description(self):
        return """Uses a good old-fashioned email address to log you in, by sending a
        "magic link" to the destination address."""

    @property
    def cb_id(self):
        return 'e'

    def __init__(self,
                 sendmail,
                 notify_cdata,
                 token_store,
                 email_template_text=DEFAULT_TEMPLATE_TEXT,
                 please_wait_error=DEFAULT_WAIT_ERROR,
                 ):
        """ Instantiate a magic link email handler. Arguments:

        from_addr -- the address that the email should be sent from
        sendmail -- a function that, given an email.message object, sends it.
            It is the responsibility of this function to set the From and
            Subject headers before it sends.
        notify_cdata -- the callback data to provide back for the notification
            response
        expires_time -- how long the email link should be valid for, in seconds (default: 900)
        email_template_text -- the plaintext template for the sent email,
            provided as a string.
        email_template_html -- the HTML template for the sent email, provided
            as a string

        Email templates get the following strings:

        {url} -- the URL that the user should visit to complete login
        {minutes} -- how long the URL is valid for, in minutes

        """

        # pylint:disable=too-many-arguments
        self._sendmail = sendmail
        self._email_template_text = email_template_text
        self._wait_error = please_wait_error
        self._lifetime = token_store.max_age or 900
        self._cdata = notify_cdata
        self._pending = token_store
        self._timeouts = expiringdict.ExpiringDict(
            max_age_seconds=86400,
            max_len=1024)

    def handles_url(self, url):
        """ Validating email by regex: not even once """
        try:
            if urllib.parse.urlparse(url).scheme == 'mailto':
                return url
        except (ValueError, AttributeError):
            pass

        if validate_email.validate_email(url):
            return 'mailto:' + url

        return None

    def initiate_auth(self, id_url, callback_uri, redir):
        # Extract the destination email from the identity URL
        dest_addr = urllib.parse.urlparse(id_url).path.lower()

        now = time.time()
        if dest_addr in self._timeouts and self._timeouts[dest_addr] > now:
            wait_time = (self._timeouts[dest_addr] - now) * 1.2
            self._timeouts[dest_addr] = now + wait_time
            return disposition.Error(self._wait_error.format(
                email=html.escape(dest_addr),
                minutes=int(math.ceil(wait_time / 60))), redir)

        token = utils.gen_token()
        link_url = (callback_uri + ('&' if '?' in callback_uri else '?') +
                    urllib.parse.urlencode({'t': token}))

        msg = email.message.EmailMessage()
        msg['To'] = dest_addr

        msg.set_content(
            self._email_template_text.format(
                url=link_url, minutes=int(math.ceil(self._lifetime / 60)))
        )

        self._sendmail(msg)

        self._pending[token] = (dest_addr, redir)
        self._timeouts[dest_addr] = now + self._lifetime / 2
        LOGGER.debug("Timeout for %s = %f", dest_addr, self._timeouts[dest_addr])

        return disposition.Notify(self._cdata)

    def check_callback(self, url, get, data):
        token = get.get('t')
        print(token, self._pending)

        if not token or token not in self._pending:
            return disposition.Error('Invalid or expired sign-in token', None)

        email_addr, redir = self._pending[token]
        del self._pending[token]

        if not email_addr or not validate_email.validate_email(email_addr):
            return disposition.Error('Invalid email address ' + html.escape(str(email_addr)), redir)

        if email_addr in self._timeouts:
            del self._timeouts[email_addr]

        return disposition.Verified('mailto:' + email_addr, redir)


def smtplib_connector(hostname, port, username=None, password=None, use_ssl=True):
    """ Generates an SMTP connection factory """

    def connect():
        import smtplib

        ctor = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        conn = ctor(hostname, port)
        if use_ssl:
            import ssl

            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            conn.ehlo()
            conn.starttls(context=context)
            conn.ehlo()
        if username or password:
            conn.login(username, password)
        return conn

    return connect


def simple_sendmail(connector, sender_address, subject):
    """ Generates a simple SMTP sendmail handler for handlers.email.Email, using
    smtplib.

    Arguments:

    connector -- a function that returns an smtplib.SMTP-compatible object in the
        connected state. Use smtplib_connector for a general-purpose connector.
    sender_address -- the email address to use for the sender
    subject -- the subject to attach to the message

    """

    def sendmail(message):
        message['From'] = sender_address
        message['Subject'] = subject

        with connector() as conn:
            return conn.sendmail(sender_address, message['To'], str(message))

    return sendmail


def from_config(config, token_store):
    """ Generate an EmailAddress handler from the provided configuration dictionary.

    Possible configuration values (all optional unless specified):

    EMAIL_SENDMAIL -- a function to call to send the email (see simple_sendmail)
    EMAIL_FROM -- the From: address to use when sending an email (required)
    EMAIL_SUBJECT -- the Subject: to use for a login email (required)
    EMAIL_CHECK_MESSAGE -- The message to send back to the user
    EMAIL_TEMPLATE_FILE -- A path to a text file for the email message
    SMTP_HOST -- the email host (required if no EMAIL_SENDMAIL)
    SMTP_PORT -- the email port (required if no EMAIL_SENDMAIL)
    SMTP_USE_SSL -- whether to use SSL for the SMTP connection
    SMTP_USERNAME -- the username to use with the SMTP server
    SMTP_PASSWORD -- the password to use with the SMTP server
    """

    if config.get('EMAIL_SENDMAIL'):
        send_func = config['EMAIL_SENDMAIL']
    else:
        connector = smtplib_connector(
            hostname=config['SMTP_HOST'],
            port=config['SMTP_PORT'],
            username=config.get('SMTP_USERNAME'),
            password=config.get('SMTP_PASSWORD'),
            use_ssl=config.get('SMTP_USE_SSL'),
        )
        send_func = simple_sendmail(connector, config['EMAIL_FROM'], config['EMAIL_SUBJECT'])

    check_message = config.get('EMAIL_CHECK_MESSAGE', 'Check your email for a login link')

    if 'EMAIL_TEMPLATE_FILE' in config:
        with open(config['EMAIL_TEMPLATE_FILE']) as file:
            email_template_text = file.read()
    else:
        email_template_text = DEFAULT_TEMPLATE_TEXT

    return EmailAddress(
        send_func,
        {'message': check_message},
        token_store,
        email_template_text=email_template_text,
    )
