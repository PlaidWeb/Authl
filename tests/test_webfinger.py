""" Tests for the webfinger mechanism """

import unittest.mock

import requests_mock

from authl import webfinger


def test_not_address():
    """ Test case: not given a webfinger address """
    with requests_mock.Mocker() as mock:
        mock.get = unittest.mock.MagicMock(side_effect=Exception)
        assert webfinger.get_profiles("http://example.com") == set()
        assert webfinger.get_profiles("foo@bar.baz") == set()
        assert webfinger.get_profiles("@quux") == set()
