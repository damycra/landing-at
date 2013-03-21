import logging


DEBUG = True
TEMPLATE_DEBUG = DEBUG

MANAGEMENT_SITE = True
SANDBOX_SITE = True

ADMINS = (
    # ('Your Name', 'your_email@domain.com'),
)

MANAGERS = ADMINS

import dj_database_url
DATABASES = {
    'default': dj_database_url.config(default='postgres://landingat:mygodthisistricky@localhost/landingat')
}

import os
REDIS_URL = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
REDIS_DBS = {
    'default': {'host': 'localhost', 'port': 6379, 'db': 0 },
    'default_bak': {'host': 'localhost', 'port': 6379, 'db': 1 }
}

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
MEDIA_URL = '*******'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Make this unique, and don't share it with anybody.
SECRET_KEY = '****'

GEOIP_PATH = '****'

REG_EMAIL = 'info@example.com'

RECURLY = {
    'username': 'api-test@example.com',
    'password': '****',
    'subdomain': '****',
}

RECURLY_HOSTED_URL = 'https://****.recurly.com/subscribe/'
