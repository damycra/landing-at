import logging
# Django settings for refs project.

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(process)d [%(threadName)s] %(levelname)s %(name)s: %(message)s')

MEDIA_URL = None
MANAGEMENT_SITE = False
SANDBOX_SITE = False

ATTENTION = 27

try:
    from env_settings import *
except:
    logging.exception('error importing env_settings')

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = None

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-gb'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

if MANAGEMENT_SITE:
 
    ROOT_URLCONF = 'refs.urls'
    
    SITE_ID = 1
    
    # If you set this to False, Django will make some optimizations so as not
    # to load the internationalization machinery.
    USE_I18N = True
    
    # If you set this to False, Django will not format dates, numbers and
    # calendars according to the current locale
    USE_L10N = True
    
    # URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
    # trailing slash.
    # Examples: "http://foo.com/media/", "/media/".
    ADMIN_MEDIA_PREFIX = '/media/'

    if SANDBOX_SITE:
        SEND_REGISTRATION_EMAIL = False
                
        MIDDLEWARE_CLASSES = (
            'django.middleware.common.CommonMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'refs.rules.middleware.SandboxMiddleware',
            'refs.rules.middleware.AccountSetupMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        )
    else:
        SEND_REGISTRATION_EMAIL = True
        
        MIDDLEWARE_CLASSES = (
            'django.middleware.common.CommonMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        )
 
    INSTALLED_APPS = (
        'refs.rules',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        #'django.contrib.sites',
        'django.contrib.messages',
        # Uncomment the next line to enable the admin:
        'django.contrib.admin',
        'django.contrib.admindocs',
        'registration',
        'refs.accounts',
        'refs.landing',
        'south',
    )
    
    TEMPLATE_CONTEXT_PROCESSORS = (
        "django.contrib.auth.context_processors.auth",
        "django.core.context_processors.debug",
        "django.core.context_processors.i18n",
        "django.contrib.messages.context_processors.messages",
        "refs.rules.context_processors.populate_website_and_user_permissions",
        "refs.utils.media_plus",)
    
    if SANDBOX_SITE:
        TEMPLATE_CONTEXT_PROCESSORS = TEMPLATE_CONTEXT_PROCESSORS + ("refs.rules.context_processors.sandbox",)
    
    AUTHENTICATION_BACKENDS = (
        'refs.accounts.backends.EmailBackend',
        'django.contrib.auth.backends.ModelBackend',
    )
    
    AUTH_PROFILE_MODULE = 'accounts.UserProfile'
    
    ACCOUNT_ACTIVATION_DAYS = 7

    MESSAGE_TAGS = {
        ATTENTION: 'attention',
    }

else:
    
    ROOT_URLCONF = 'refs.landing.urls'
    # If you set this to False, Django will make some optimizations so as not
    # to load the internationalization machinery.
    USE_I18N = False
    
    # If you set this to False, Django will not format dates, numbers and
    # calendars according to the current locale
    USE_L10N = False
    
    MIDDLEWARE_CLASSES = ('refs.landing.middleware.ExceptionHandlingMiddleware',)
    
    INSTALLED_APPS = (
        'refs.rules',
        'refs.landing',
    )
    
    TEMPLATE_CONTEXT_PROCESSORS = ()
