""" Handler for emailing a magic link """

import email
import urllib.parse

import validate_email
import ska

from . import Handler
from .. import disposition


DEFAULT_TEMPLATE_TEXT = """\
Hello! Someone, possibly you, asked to log in using this email address. If this
was you, please visit the following link within the next {minutes} minutes:

    {url}

If this wasn't you, you can safely disregard this message.

"""


class EmailAddress(Handler):
    """ Email via "magic link" """

    def __init__(self,
                 secret_key,
                 sendmail,
                 notify_cdata,
                 expires_time=None,
                 email_template_text=DEFAULT_TEMPLATE_TEXT,
                 ):
        """ Instantiate a magic link email handler. Arguments:

        from_addr -- the address that the email should be sent from
        secret_key -- a secret key for the authentication algorithm to use.
            This should be a fixed value that is configured outside of code
            (e.g. via an environment variable)
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
        self._lifetime = expires_time or 900
        self._cdata = notify_cdata

        self._cfg = {
            'secret_key': secret_key,
            'signature_param': 's',
            'auth_user_param': 'u',
            'valid_until_param': 'v',
            'extra_param': 'e',
        }

    def service_name(self):
        return 'Email'

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
            **self._cfg
        )

        msg = email.message.EmailMessage()
        msg['To'] = dest_addr

        msg.set_content(
            self._email_template_text.format(url=link_url, minutes=self._lifetime / 60)
        )

        self._sendmail(msg)

        return disposition.Notify(self._cdata)

    def check_callback(self, url, get, data):
        validation = ska.validate_signed_request_data(data=get, **self._cfg)

        if validation.result:
            return disposition.Verified(get[self._cfg['auth_user_param']])

        return disposition.Error(','.join(validation.reason))


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


def from_config(config, secret_key):
    """ Generate an EmailAddress handler from the provided configuration directory.

    Possible configuration values (all optional unless specified):

    SMTP_HOST -- the email host (required)
    SMTP_PORT -- the email port (required)
    SMTP_USE_SSL -- whether to use SSL for the SMTP connection
    SMTP_USERNAME -- the username to use with the SMTP server
    SMTP_PASSWORD -- the password to use with the SMTP server
    EMAIL_FROM -- the From: address to use when sending an email (required)
    EMAIL_SUBJECT -- the Subject: to use for a login email (required)
    EMAIL_LOGIN_TIMEOUT -- How long (in seconds) the user has to follow the login link
    EMAIL_CHECK_MESSAGE -- The message to send back to the user
    EMAIL_TEMPLATE_FILE -- A path to a text file for the email message
    """

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
        secret_key,
        send_func,
        {'message': check_message},
        expires_time=config.get('EMAIL_LOGIN_TIMEOUT'),
        email_template_text=email_template_text,
    )
