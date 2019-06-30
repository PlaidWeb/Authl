# Authl
A library for managing federated identity

## Current state

Just a design in my head.

## Design goals

High-level goal: Make it easy to provide federated identity to Python 3-based web apps (with a particular focus on [Publ](https://github.com/PlaidWeb/Publ))

This library should enable the following:

* Given a URL, determine whether an identity can be established against that URL
* Provide multiple identity backends for different URL schemata, including but not limited to:
    * OpenID 1.x
    * IndieAuth
    * Email
    * Various OAuth providers (twitter, facebook, etc.)
    * Mastodon
    * Local username/password
* Each backend should be optional and configurable
* Provide default (optional) Flask endpoints for the various endpoints (URL validation, success callbacks, etc.)

## Roadmap

Rough expected order of implementation:

1. Email magic links (which provides access for basically everyone)
1. IndieAuth (possibly using IndieLogin.com for the hard parts)
1. OpenID 1.x (which provides access for Dreamwidth, Wordpress, Launchpad, and countless other site users)
1. Everything else

## Rationale

Identity is hard, and there are so many competing standards which try to be the be-all end-all Single Solution. Many of them are motivated by their own politics; OAuth wants lock-in to silos, IndieAuth wants every user to self-host their own identity fully and not support silos at all, etc., and users just want to be able to log in with the social media they're already using (siloed or not).

Any solution which requires all users to have a certain minimum level of technical ability is not a workable solution.

All of these solutions are prone to the so-called "NASCAR problem" where every supported login provider needs its own UI. But being able to experiment with a more unified UX might help to fix some of that.
