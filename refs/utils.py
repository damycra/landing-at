from django import forms
from django.db import models
from django.utils.translation import ugettext_lazy as _
import random
import datetime
import sys
import traceback
from django.core.context_processors import media
from refs import settings
import re
from django.template.loader import render_to_string
from django.contrib import messages
from refs.settings import ATTENTION


def random_token(seq='0123456789'):
    return "%s%s" % (str((datetime.datetime.now() - datetime.datetime(2008, 1, 12)).days) 
                     ,"".join(random.sample(seq,8)) )

def random_uid():
    return random.randint(1, 2147483000)

def is_secure(request):
    return request.is_secure() or request.META.get('HTTP_X_FWDED_PORT', False) == '443'

_rex = re.compile(r'^http://cdn', re.IGNORECASE)

def media_plus(request):
    dict = media(request)
    
    if is_secure(request):
        if getattr(settings, 'SECURE_MEDIA', True):
            media_url = dict.get('MEDIA_URL', settings.MEDIA_URL)
            dict['MEDIA_URL'] = _rex.sub('https://ssl', media_url)

    return dict

#class StripCharField(forms.CharField):
#    def __init__(self, strip=True, *args, **kwargs):
#        self.strip = strip
#        super(StripCharField, self).__init__(*args, **kwargs)
#
#    def to_python(self, value):
#        val = super(StripCharField, self).to_python(value)
#        return val.strip() if self.strip else val
#
#
#class ModelStripCharField(models.CharField):
#    description = _("String (up to %(max_length)s), optionally stripped")
#
#    def __init__(self, strip=True, *args, **kwargs):
#        super(ModelStripCharField, self).__init__(*args, **kwargs)
#        self.strip = strip
#        
#    def get_internal_type(self):
#        return "StripCharField"
#
#    def formfield(self, **kwargs):
#        defaults = {'form_class': StripCharField, 'strip': self.strip}
#        defaults.update(kwargs)
#        return super(ModelStripCharField, self).formfield(**defaults)

def get_client_ip(request):
    return request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1'))

def format_exception_info(maxTBlevel=10):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    try:
        excArgs = exc.__dict__["args"]
    except KeyError:
        excArgs = "<no args>"
    excTb = traceback.format_tb(trbk, maxTBlevel)
    return (excName, excArgs, excTb)

def set_message(request, template, level='success', context=None):
    msg = render_to_string('messages/%s.html' % template, context)
    if level == 'warning':
        messages.warning(request, msg)
    elif level == 'error':
        messages.error(request, msg)
    elif level == 'info':
        messages.info(request, msg)
    elif level == 'attention':
        messages.add_message(request, ATTENTION, msg)
    else:
        messages.success(request, msg)
        

def get_website_redis_key(token):
    return 'nv:website:%s' % token

def get_website_age_redis_key(token):
    return 'nv:website:age:%s' % token

def get_pageview_redis_key():
    return 'lst:pageviews' 

def get_website_refresh_redis_key():
    return 'list:expired_websites'

def get_visits_redis_key(token, client_identifier):
    return 'zst:visits:%s:%s' % (token, client_identifier)

def get_filter_hits_redis_key(token, filter_id):
    return 'nv:filter:%s:%s' % (token, filter_id)

def get_filter_hits_by_day_redis_key(token, filter_id, date):
    return 'nv:filter:%s:%s:%s' % (token, filter_id, date.strftime('%Y%m%d'))

def get_filter_hits_by_month_redis_key(token, filter_id, date):
    return 'nv:filter:%s:%s:%s' % (token, filter_id, date.strftime('%Y%m'))
