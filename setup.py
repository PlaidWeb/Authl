"""Setup for AUthl packaging"""

from distutils.util import convert_path
from os import path

# Always prefer setuptools over distutils
from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md')) as f:
    long_description = f.read()

main_ns = {}
ver_path = convert_path('authl/__version__.py')
with open(ver_path) as ver_file:
    exec(ver_file.read(), main_ns)

setup(
    name='Authl',

    version=main_ns['__version__'],

    description='Genericized multi-protocol authentication wrapper',

    long_description=long_description,

    long_description_content_type='text/markdown',

    url='https://github.com/PlaidWeb/Authl',

    author='fluffy',
    author_email='fluffy@beesbuzz.biz',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Internet :: WWW/HTTP :: Session',
    ],

    keywords='authentication openid indieauth login',

    packages=find_packages(),

    package_data={'authl': ['flask_templates/*']},

    install_requires=[
        'beautifulsoup4',
        'expiringdict',
        'read_only_property',
        'requests',
        'requests_oauthlib',
        'validate_email',
    ],

    extras_require={'dev': [
        'autopep8',
        'flake8',
        'flask',
        'isort',
        'mypy',
        'pylint',
        'twine',
    ]},

    project_urls={
        'Bug Reports': 'https://github.com/PlaidWeb/Authl/issues',
        'Source': 'https://github.com/PlaidWeb/Authl/',
        'Discord': 'https://beesbuzz.biz/discord',
        'Funding': 'https://liberapay.com/fluffy',
    },

    python_requires='>=3.5',
)
