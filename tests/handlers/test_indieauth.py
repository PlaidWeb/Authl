""" Tests of the IndieAuth handler """
# pylint:disable=missing-docstring


import requests_mock


def test_find_endpoint_by_url():
    from authl.handlers.indieauth import find_endpoint
    with requests_mock.Mocker() as mock:
        mock.get('http://link.absolute/', text='Nothing to see',
                 headers={'Link': '<https://endpoint/>; rel="authorization_endpoint"'})

        assert find_endpoint('http://link.absolute/') == 'https://endpoint/'

        mock.get('http://link.relative/', text='Nothing to see',
                 headers={'Link': '<invalid>; rel="authorization_endpoint"'})
        assert find_endpoint('http://link.relative/') == 'invalid'

        mock.get('http://content.absolute/',
                 text='<link rel="authorization_endpoint" href="https://endpoint/">')
        assert find_endpoint('http://content.absolute/') == 'https://endpoint/'

        mock.get('http://content.relative/',
                 text='<link rel="authorization_endpoint" href="endpoint" >')
        assert find_endpoint('http://content.relative/') == 'http://content.relative/endpoint'

        mock.get('http://nothing/', text='nothing')
        assert find_endpoint('http://nothing/') is None

        # test the caching
        mock.reset()

        assert find_endpoint('http://link.absolute/') == 'https://endpoint/'
        assert find_endpoint('http://link.relative/') == 'invalid'
        assert find_endpoint('http://content.absolute/') == 'https://endpoint/'
        assert find_endpoint('http://content.relative/') == 'http://content.relative/endpoint'

        assert not mock.called

        # but a failed lookup shouldn't be cached
        assert find_endpoint('http://nothing/') is None
        assert mock.called
