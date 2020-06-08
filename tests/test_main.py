""" main instance tests """

from authl import Authl

from . import TestHandler


class UrlHandler(TestHandler):
    """ a handler that just handles a specific URL """

    def __init__(self, url, cid):
        self.url = url
        self.cid = cid

    @property
    def cb_id(self):
        return self.cid

    def handles_url(self, url):
        return url if url == self.url else None


def test_register_handler():
    """ Test that both registration paths result in the same, correct result """
    handler = TestHandler()

    instance_1 = Authl([handler])
    assert list(instance_1.handlers) == [handler]

    instance_2 = Authl()
    instance_2.add_handler(handler)

    assert list(instance_1.handlers) == list(instance_2.handlers)


def test_get_handler_for_url():
    """ Test that URL rules map correctly """
    handler_1 = UrlHandler('test://foo', 'a')
    handler_2 = UrlHandler('test://bar', 'b')
    instance = Authl([handler_1, handler_2])

    assert instance.get_handler_for_url('test://foo') == (handler_1, 'a', 'test://foo')
    assert instance.get_handler_for_url('test://bar') == (handler_2, 'b', 'test://bar')
    assert instance.get_handler_for_url('test://baz') == (None, '', '')
