# Create your views here.
from django.shortcuts import render_to_response
from refs.landing.records import save_page_view,\
    get_website, WrongWebsite, save_visit_start, get_redis
import datetime
import urllib
import urlparse
import re
from refs.utils import format_exception_info

import logging
from django.http import HttpResponseNotFound, HttpResponseServerError,\
    HttpResponse
import sys


def get_and_check_website(request, token, location):
    
    website = get_website(token)

    # check the page request is coming from the correct website
    referring_page = request.META.get('HTTP_REFERER', location)
    if referring_page:
        parsed = urlparse.urlparse(referring_page)
        patt = '%s%s' % ('' if website.exact_match else '(.*[.])?', website.name)
        if not re.match(patt, parsed.hostname, re.IGNORECASE):
            raise WrongWebsite('website %s [%s] does not match referrer [%s]' % (website.name, token, referring_page))
    
    if referring_page != location:
        logging.info('referrer header (%s) does not match JS value (%s)' % (referring_page, location))
    
    return website

def store_page_view(location, client_identifier, token, new_visit, view_date, filters):
    page_view_dict = {'location': location,
                 'client_identifier': client_identifier,
                 'token': token,
                 'visit_start': new_visit,
                 'view_date': datetime.datetime.utcnow(),
                 'filters': [f.id for f in filters] }

    save_page_view(page_view_dict)
    

def get_messages(request):
    try:
        #retrieve required request parameters
        token = request.GET.get('t', None)    
        location =  urllib.unquote_plus(request.GET.get('l', None))
        client_identifier = request.GET.get('c', False) 
        new_visit = (client_identifier and request.GET.get('n', False)) != False
        
        website = get_and_check_website(request, token, location)
        view_date = datetime.datetime.utcnow()
        
        if new_visit: #frequent visitor handler may need this information to hand
            save_visit_start(token, client_identifier, view_date)
        
        request.redis = get_redis()
                    
        #basic checks performed and website object obtained
        filters = website.check_filters(request)
        
        #store the view
        store_page_view(location, client_identifier, token, new_visit, view_date, filters)
        
        if len(filters) == 0:
            return HttpResponse(status=204, mimetype='application/javascript')
                    
        return render_to_response('landing/message.js', {'filters': filters}, mimetype='application/javascript')
    except WrongWebsite:
        exc = format_exception_info()
        logging.info('wrong website: %s;%s;' % (exc[0], exc[1]), exc_info=sys.exc_info() )
        return bare_404(request)
    except:
        exc = format_exception_info()
        logging.error('Error in get_messages: %s;%s;' % (exc[0], exc[1]), exc_info=sys.exc_info() )
        return HttpResponseServerError()     


def bare_404(request):
    return HttpResponseNotFound('Not found')


def filter_fired(request):
    try:
        #retrieve required request parameters
        token = request.GET.get('t', None)    
        uid = request.GET.get('u', False) 
        
        request.redis = get_redis()
        
        #store the view
        store_page_view(location, client_identifier, token, new_visit, view_date, filters)
        
        if len(filters) == 0:
            return HttpResponse(status=204, mimetype='application/javascript')
                    
        return render_to_response('landing/message.js', {'filters': filters}, mimetype='application/javascript')
    except WrongWebsite:
        exc = format_exception_info()
        logging.info('wrong website: %s;%s;' % (exc[0], exc[1]), exc_info=sys.exc_info() )
        return bare_404(request)
    except:
        exc = format_exception_info()
        logging.error('Error in get_messages: %s;%s;' % (exc[0], exc[1]), exc_info=sys.exc_info() )
        return HttpResponseServerError()

