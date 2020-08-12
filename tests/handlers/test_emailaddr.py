""" Tests for email login """
# pylint:disable=missing-docstring

import logging
import unittest.mock

from authl import disposition, tokens
from authl.handlers import email_addr

from . import parse_args

LOGGER = logging.getLogger(__name__)


def test_basics():
    handler = email_addr.EmailAddress(None, None, tokens.DictStore())
    assert handler.service_name == 'Email'
    assert handler.url_schemes
    assert 'email' in handler.description
    assert handler.cb_id == 'e'
    assert handler.logo_html[0][1] == 'Email'

    assert handler.handles_url('foo@bar.baz') == 'mailto:foo@bar.baz'
    assert handler.handles_url('mailto:foo@bar.baz') == 'mailto:foo@bar.baz'
    assert not handler.handles_url('mailto:foobar.baz')
    assert not handler.handles_url('@foo@bar.baz')
    assert not handler.handles_url('https://example.com/')


def test_success():
    store = {}

    def do_callback(message):
        assert message['To'] == 'user@example.com'

        url = message.get_payload().strip()
        args = parse_args(url)

        assert url.startswith('http://example/cb/')

        result = handler.check_callback(url, parse_args(url), {})
        LOGGER.info('check_callback(%s,%s): %s', url, args, result)

        assert isinstance(result, disposition.Verified)
        assert result.identity == 'mailto:user@example.com'
        assert result.redir == '/redir'

    handler = email_addr.EmailAddress(do_callback, 'some data', tokens.DictStore(store),
                                      email_template_text='{url}')

    result = handler.initiate_auth('mailto:user@example.com', 'http://example/cb/', '/redir')
    LOGGER.info('initiate_auth: %s', result)
    assert isinstance(result, disposition.Notify)
    assert result.cdata == 'some data'


def test_failures():
    store = {}
    pending = {}

    def accept(message):
        url = message.get_payload().strip()
        pending[message['To']] = url

    handler = email_addr.EmailAddress(accept,
                                      'some data', tokens.DictStore(store),
                                      10,
                                      email_template_text='{url}')

    # must be well-formed mailto: URL
    for malformed in ('foo@bar.baz', 'http://foo.bar/', 'mailto:blahblahblah'):
        assert 'Malformed' in str(handler.initiate_auth(malformed,
                                                        'http://example.cb/',
                                                        '/malformed'))

    # check for missing or invalid tokens
    assert 'Missing token' in str(handler.check_callback('foo', {}, {}))
    assert 'Invalid token' in str(handler.check_callback('foo', {'t': 'bogus'}, {}))

    def initiate(addr, redir):
        result = handler.initiate_auth('mailto:' + addr, 'http://example/', redir)
        assert isinstance(result, disposition.Notify)
        assert result.cdata == 'some data'

    def check_pending(addr):
        url = pending[addr]
        return handler.check_callback(url, parse_args(url), {})

    # check for timeout failure
    with unittest.mock.patch('time.time') as mock_time:
        mock_time.return_value = 30

        assert len(store) == 0
        initiate('timeout@example.com', '/timeout')
        assert len(store) == 1

        mock_time.return_value = 20000

        result = check_pending('timeout@example.com')
        assert isinstance(result, disposition.Error)
        assert 'timed out' in result.message
        assert result.redir == '/timeout'
        assert len(store) == 0

    # check for replay attacks
    assert len(store) == 0
    initiate('replay@example.com', '/replay')
    assert len(store) == 1
    result1 = check_pending('replay@example.com')
    result2 = check_pending('replay@example.com')
    assert len(store) == 0

    assert isinstance(result1, disposition.Verified)
    assert result1.identity == 'mailto:replay@example.com'
    assert result1.redir == '/replay'
    assert isinstance(result2, disposition.Error)
    assert 'Invalid token' in str(result2)


def test_connector():
    with unittest.mock.patch('smtplib.SMTP_SSL') as mock_smtp_ssl,\
            unittest.mock.patch('ssl.SSLContext') as mock_ssl:
        import ssl

        conn = unittest.mock.MagicMock()
        mock_smtp_ssl.return_value = conn

        connector = email_addr.smtplib_connector('localhost', 25,
                                                 'test', 'poiufojar',
                                                 use_ssl=True)
        connector()

        mock_smtp_ssl.assert_called_with('localhost', 25)
        mock_ssl.assert_called_with(ssl.PROTOCOL_TLS_CLIENT)
        conn.ehlo.assert_called()
        conn.starttls.assert_called()
        conn.login.assert_called_with('test', 'poiufojar')


def test_simple_sendmail():
    connector = unittest.mock.MagicMock(name='connector')

    import email
    message = email.message.EmailMessage()
    message['To'] = 'recipient@bob.example'
    message.set_payload('test body')

    sender = email_addr.simple_sendmail(connector, 'sender@bob.example', 'test subject')

    sender(message)
    connector.assert_called_once()

    with connector() as conn:
        conn.sendmail.assert_called_with('sender@bob.example',
                                         'recipient@bob.example',
                                         str(message))
    assert message['From'] == 'sender@bob.example'
    assert message['Subject'] == 'test subject'


def test_from_config():
    store = {}
    mock_open = unittest.mock.mock_open(read_data="test template content")

    with unittest.mock.patch('smtplib.SMTP') as mock_smtp,\
            unittest.mock.patch('builtins.open', mock_open):
        conn = unittest.mock.MagicMock()
        mock_smtp.return_value = conn

        handler = email_addr.from_config({
            'EMAIL_FROM': 'sender@example.com',
            'EMAIL_SUBJECT': 'test subject',
            'EMAIL_CHECK_MESSAGE': 'check yr email',
            'EMAIL_TEMPLATE_FILE': 'template.txt',
            'EMAIL_EXPIRE_TIME': 37,
            'SMTP_HOST': 'smtp.example.com',
            'SMTP_PORT': 587,
            'SMTP_USE_SSL': False,
        }, tokens.DictStore(store))

        mock_open.assert_called_with('template.txt')
        res = handler.initiate_auth('mailto:alice@bob.example', 'http://cb/', '/redir')
        assert res.cdata['message'] == 'check yr email'

        assert len(store) == 1
        mock_smtp.assert_called_with('smtp.example.com', 587)


def test_please_wait():
    token_store = tokens.DictStore()
    pending = {}
    mock_send = unittest.mock.MagicMock()
    handler = email_addr.EmailAddress(mock_send, "this is data", token_store,
                                      expires_time=60,
                                      pending_storage=pending)

    with unittest.mock.patch('time.time') as mock_time:
        assert mock_send.call_count == 0
        mock_time.return_value = 10

        # First auth should call mock_send
        handler.initiate_auth('mailto:foo@bar.com', 'http://example/', 'blop')
        assert mock_send.call_count == 1
        assert 'foo@bar.com' in pending
        token_value = pending['foo@bar.com']

        # Second auth should not
        handler.initiate_auth('mailto:foo@bar.com', 'http://example/', 'blop')
        assert mock_send.call_count == 1
        assert 'foo@bar.com' in pending
        assert token_value == pending['foo@bar.com']

        # Using the link should remove the pending item
        handler.check_callback('http://example/', {'t': pending['foo@bar.com']}, {})
        assert 'foo@bar.com' not in pending

        # Next auth should call mock_send again
        handler.initiate_auth('mailto:foo@bar.com', 'http://example/', 'blop')
        assert mock_send.call_count == 2
        assert 'foo@bar.com' in pending
        assert token_value != pending['foo@bar.com']
        token_value = pending['foo@bar.com']

        # Timing out the token should cause it to send again
        mock_time.return_value = 1000
        handler.initiate_auth('mailto:foo@bar.com', 'http://example/', 'blop')
        assert mock_send.call_count == 3
        assert 'foo@bar.com' in pending
        assert token_value != pending['foo@bar.com']
        token_value = pending['foo@bar.com']

        # And anything else that removes the token from the token_store should as well
        token_store.remove(pending['foo@bar.com'])
        handler.initiate_auth('mailto:foo@bar.com', 'http://example/', 'blop')
        assert mock_send.call_count == 4
        assert token_value != pending['foo@bar.com']
        token_value = pending['foo@bar.com']
