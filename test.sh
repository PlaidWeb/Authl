#!/bin/sh

poetry install
FLASK_DEBUG=1 FLASK_APP=test_app.py poetry run flask run
