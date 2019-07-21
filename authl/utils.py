""" Utility functions """

import base64
import uuid


def gen_token():
    """ Generate a random URL-safe token string """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().replace('=', '')
