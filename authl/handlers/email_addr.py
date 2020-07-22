"""
Email handler
=============

This handler emails a "magic link" to the user so that they can log in that way.
It requires an SMTP server of some sort; see your hosting provider's
documentation for the appropriate configuration. This should also be able to
work with your regular email provider.

See :py:func:`from_config` for the simplest configuration mechanism.

"""

import email
import logging
import math
import time
import urllib.parse

import validate_email

from .. import disposition, tokens, utils
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
        return """Uses email to log you in, by sending a "magic link" to the
        destination address."""

    @property
    def cb_id(self):
        return 'e'

    @property
    def logo_html(self):
        return [(utils.read_icon('email_addr.svg'), 'Email')]

    def __init__(self,
                 sendmail,
                 notify_cdata,
                 token_store: tokens.TokenStore,
                 expires_time=None,
                 email_template_text=DEFAULT_TEMPLATE_TEXT,
                 please_wait_error=DEFAULT_WAIT_ERROR,
                 ):
        """ Instantiate a magic link email handler.

        :param sendmail: A function that, given an :py:class:`email.message`
            object, sends it. It is the responsibility of this function to set
            the From and Subject headers before it sends.
        :param notify_cdata: the callback data to provide to the user for the
            next step instructions
        :param int expires_time: how long the email link should be valid for, in
            seconds (default: 900)
        :param str email_template_text: the plaintext template for the sent
            email, provided as a template string

        Email templates are formatted with the following parameters:

        * ``{url}``: the URL that the user should visit to complete login
        * ``{minutes}``:  how long the URL is valid for, in minutes

        """

        # pylint:disable=too-many-arguments
        self._sendmail = sendmail
        self._email_template_text = email_template_text
        self._wait_error = please_wait_error
        self._cdata = notify_cdata
        self._token_store = token_store
        self._lifetime = expires_time or 900

    def handles_url(self, url):
        """
        Accepts any email address formatted as ``user@example.com`` or
        ``mailto:user@example.com``. The actual address is validated using
        :py:mod:`validate_email`.
        """

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == 'mailto' and validate_email.validate_email(parsed.path):
            return url
        if parsed.scheme:
            return None

        if validate_email.validate_email(url):
            return 'mailto:' + url

        return None

    def initiate_auth(self, id_url, callback_uri, redir):
        parsed = urllib.parse.urlparse(id_url)
        if parsed.scheme != 'mailto' or not validate_email.validate_email(parsed.path):
            return disposition.Error("Malformed email URL", redir)
        dest_addr = parsed.path.lower()

        token = self._token_store.put((dest_addr, redir, time.time()))

        link_url = (callback_uri + ('&' if '?' in callback_uri else '?') +
                    urllib.parse.urlencode({'t': token}))

        msg = email.message.EmailMessage()
        msg['To'] = dest_addr

        msg.set_content(
            self._email_template_text.format(
                url=link_url, minutes=int(math.ceil(self._lifetime / 60)))
        )

        self._sendmail(msg)

        return disposition.Notify(self._cdata)

    def check_callback(self, url, get, data):
        token = get.get('t')

        if not token:
            return disposition.Error('Missing token', None)

        try:
            email_addr, redir, when = self._token_store.pop(token)
        except (KeyError, ValueError):
            return disposition.Error('Invalid token', '')

        if time.time() > when + self._lifetime:
            return disposition.Error("Login timed out", redir)

        return disposition.Verified('mailto:' + email_addr, redir)


def smtplib_connector(hostname, port, username=None, password=None, use_ssl=False):
    """ A utility class that generates an SMTP connection factory.

    :param str hostname: The SMTP server's hostname
    :param int port: The SMTP server's connection port
    :param str username: The SMTP server username
    :param str password: The SMTP server port
    :param bool use_ssl: Whether to use SSL

    """

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
    """ A simple SMTP sendmail handler.

    :param function connector: A factory-type function that returns an
        :py:class:`smtplib.SMTP`-compatible object in the connected state.
        Use :py:func:`smtplib_connector` for an easy-to-use general-purpose
        connector.
    :param str sender_address: The email address to use for the sender
    :param str subject: the subject line to attach to the message

    Returns a function that, when called with an
    :py:class:`email.message.EmailMessage`, sets the `From` and `Subject` lines
    and sends the message via the provided connector.

    """

    def sendmail(message: email.message.EmailMessage):
        message['From'] = sender_address
        message['Subject'] = subject

        with connector() as conn:
            return conn.sendmail(sender_address, message['To'], str(message))

    return sendmail


def from_config(config, token_store: tokens.TokenStore):
    """

    Generate an :py:class:`EmailAddress` handler from the provided configuration
    dictionary.

    :param dict config: The configuration settings for the handler. Relevant
        keys:

        * ``EMAIL_SENDMAIL``: a function to call to send the email (defaults to
            using :py:func:`simple_sendmail`)

        * ``EMAIL_FROM``: the ``From:`` address to use when sending an email

        * ``EMAIL_SUBJECT``: the ``Subject:`` to use for a login email

        * ``EMAIL_CHECK_MESSAGE``: The :py:class:`authl.disposition.Notify` client
            data. Defaults to a simple string-based message.

        * ``EMAIL_TEMPLATE_FILE``: A path to a text file for the email message; if
            not specified a default template will be used.

        * ``EMAIL_EXPIRE_TIME``: How long a login email is valid for, in seconds
            (defaults to the :py:class:`EmailAddress` default value)

        * ``SMTP_HOST``: the outgoing SMTP host (required if no
            ``EMAIL_SENDMAIL``)

        * ``SMTP_PORT``: the outgoing SMTP port (required if no ``EMAIL_SENDMAIL``)

        * ``SMTP_USE_SSL``: whether to use SSL for the SMTP connection (defaults
            to ``False``). It is *highly recommended* to set this to `True` if
            your ``SMTP_HOST`` is anything other than `localhost`.

        * ``SMTP_USERNAME``: the username to use with the SMTP server

        * ``SMTP_PASSWORD``: the password to use with the SMTP server

    :param tokens.TokenStore token_store: the authentication token storage
        mechanism; see :py:mod:`authl.tokens` for more information.

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
        expires_time=config.get('EMAIL_EXPIRE_TIME'),
        email_template_text=email_template_text,
    )
