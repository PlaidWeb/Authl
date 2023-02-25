""" Tests for the webfinger mechanism """
# pylint:disable=missing-docstring


from authl import webfinger


def test_not_address(requests_mock):
    assert webfinger.get_profiles("http://example.com") == set()
    assert webfinger.get_profiles("foo@bar.baz") == set()
    assert webfinger.get_profiles("@quux") == set()

    assert not requests_mock.called


def test_no_resource(requests_mock):
    requests_mock.get('https://example.com/.well-known/webfinger?resource=acct:404@example.com',
                      status_code=404)
    assert webfinger.get_profiles("@404@example.com") == {"https://example.com/@404"}


def test_resource(requests_mock):
    requests_mock.get('https://example.com/.well-known/webfinger?resource=acct:profile@example.com',
                      json={
                          "links": [{
                              "rel": "profile",
                              "href": "https://profile.example.com/u/moo"
                          }, {
                              "rel": "self",
                              "href": "https://profile.example.com/u/moo"
                          }, {
                              "rel": "self",
                              "href": "https://self.example.com/u/moo"
                          }, {
                              "rel": "posts",
                              "href": "https://example.com/u/moo/posts"
                          }]
                      })
    assert webfinger.get_profiles(
        "@profile@example.com") == {'https://profile.example.com/u/moo',
                                    'https://self.example.com/u/moo'}
    assert webfinger.get_profiles(
        "acct:profile@example.com") == {'https://profile.example.com/u/moo',
                                        'https://self.example.com/u/moo'}

    requests_mock.get('https://example.com/.well-known/webfinger?resource=acct:empty@example.com',
                      json={
                          "links": [{
                              "rel": "nothing",
                              "href": "https://profile.example.com/u/moo"
                          }, {
                              "rel": "still-nothing",
                              "href": "https://self.example.com/u/moo"
                          }, {
                              "rel": "posts",
                              "href": "https://example.com/u/moo/posts"
                          }]
                      })

    assert webfinger.get_profiles("@empty@example.com") == set()


def test_invalid(requests_mock):
    requests_mock.get('https://example.com/.well-known/webfinger?resource=acct:invalid@example.com',
                      text="""This is not valid JSON""")
    assert webfinger.get_profiles('@invalid@example.com') == set()
