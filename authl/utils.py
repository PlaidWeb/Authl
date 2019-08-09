""" Utility functions """

import base64
import uuid


def gen_token():
    """ Generate a random URL-safe token string """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().replace('=', '')


def read_file(filename):
    """ Given a filename, read the entire thing into a string """
    with open(filename) as file:
        return file.read()
