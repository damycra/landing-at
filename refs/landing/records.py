from refs.landing.models import PageViewRecord, FilterFiredRecord, Url,\
    ClientVisitStart
import logging
import threading
import redis
from redis import RedisError
from refs.utils import format_exception_info, get_website_redis_key,\
    get_pageview_redis_key, get_visits_redis_key, random_uid,\
    get_filter_hits_redis_key, get_filter_hits_by_day_redis_key,\
    get_website_age_redis_key, get_website_refresh_redis_key,\
    get_filter_hits_by_month_redis_key
from refs.settings import REDIS_URL
from refs.rules.models import Website
import time
from django.db import transaction
import datetime
try:
    import cPickle as pickle
except:
    import pickle


class WrongWebsite(Exception):
    pass

#############
# REDIS stuff
#############
try:
    _redis = redis.from_url(REDIS_URL) #Redis(**REDIS_DBS['default'])
    _redis.is_backup = False
except:
    exc = format_exception_info()
    logging.error('redis error: %s' % (exc))
    try:
        _redis = redis.from_url(REDIS_URL) # Redis(host=REDIS_DBS['default_bak']['host'], port=REDIS_DBS['default_bak']['port'])
        _redis.is_backup = True
    except:
        exc2 = format_exception_info()
        logging.error('redis backup error: %s' % (exc2))

logging.info('redis initialised in [%s] mode on thread [%s]' % ('backup' if _redis.is_backup else 'standard', threading.currentThread().getName()))

def get_redis(backup=False):
    key = 'default' if not backup else 'default_bak'
    #_redis.select(**REDIS_DBS[key])
    _redis.is_backup = backup
    return _redis

def switch_redis():
    return get_redis(backup=(not _redis.is_backup))    

def cache_website(website, website_key, redis=None):
    try:
        redis = redis or get_redis()
        redis.set(website_key, pickle.dumps(website))
        redis.set(get_website_age_redis_key(website.token), time.mktime(website.updated_date.timetuple()))
    except RedisError:
        exc = format_exception_info()
        logging.error('redis: failed to save pickled website key %s\n%s' % (website_key, exc))

def unpickle_from_redis(key, redis=None, auto_fallback=True):
    try:
        redis = redis or get_redis()
        pickled = redis.get(key)
    except RedisError:
        exc = format_exception_info()
        logging.error('redis%s: failed to load website: %s' % (' backup' if redis.is_backup else ' standard' , exc))
        pickled =  None

    if not pickled and auto_fallback:
        redis = switch_redis()
        return unpickle_from_redis(key, redis, auto_fallback=False)
    else:
        return pickle.loads(pickled) if pickled else None
    
    
#############
# LIVE landing.at stuff
#############

def get_website(token):
    website_key = get_website_redis_key(token)
    website = unpickle_from_redis(website_key)
                       
    if not website: #last chance
        website = get_website_from_db(token)
        cache_website(website, website_key)
    
    return website
        

def get_website_from_db(token):
    try:
        website = Website.objects.select_related().get(token=token)
    except Website.DoesNotExist:
        raise WrongWebsite('website token [%s] not found' % token) 
    else: # populate everything
        website.prepare()
            
    return website

 

def save_page_view(page_view_dict, switch=True, redis=None):
    try:
        redis = redis or get_redis()
        page_view_dict['uid'] = random_uid()
        redis.lpush(get_pageview_redis_key(), pickle.dumps(page_view_dict))
    except RedisError:
        exc = format_exception_info()
        logging.error('redis: failed to save page view\n%s' % (exc))
        if switch:
            logging.info('switching redis...')
            save_page_view(page_view_dict, switch=False, redis=switch_redis())
        else:
            save_page_view_to_db(page_view_dict)


def save_visit_start(token, client_identifier, visit_date):
    key = get_visits_redis_key(token, client_identifier)
    score = time.mktime(visit_date.timetuple())
    redis = get_redis()
    redis.zadd(key, score, score)
        

@transaction.commit_on_success        
def save_page_view_to_db(page_view_dict):
    location_url = get_or_save_url(page_view_dict['location'])
    
    if not PageViewRecord.objects.filter(website_token=page_view_dict['token'], view_date=page_view_dict['view_date'], uid=page_view_dict['uid']).exists():
        page_view = PageViewRecord(website_token=page_view_dict['token'], location=location_url, 
                               view_date=page_view_dict['view_date'], uid=page_view_dict['uid'])
        page_view.save()
        for id in page_view_dict['filters']:
            FilterFiredRecord(filter_id=id, page_view=page_view).save()

        if page_view_dict['visit_start']:
            ClientVisitStart(website_token=page_view_dict['token'], client_identifier=page_view_dict['client_identifier'], visit_date=page_view_dict['view_date']).save()
            
        return True
    
    return False    

def get_or_save_url(url):
    url_obj = None
    
    if url:
        loop = 0
        while url_obj == None and loop < 2:
            try:
                url_obj = Url.objects.get(url__iexact=url)
            except Url.DoesNotExist:
                try:
                    Url(url=url).save()
                except:
                    pass
            loop = loop + 1
    
    return url_obj


def refresh_cache_for_all_websites():
    websites = Website.objects.all()
    for backup in [True, False]:
        redis = get_redis(backup=backup) 
        for website in websites:
            logging.info('Check and refresh cache for %s on %s redis' % (website.name, 'backup' if backup else 'standard'))
            _refresh_cache_for_website(website, redis)

def _refresh_cache_for_website(website, redis):
    age = redis.get(get_website_age_redis_key(website.token)) or 0
    if float(age) < time.mktime(website.updated_date.timetuple()):
        website.prepare()
        logging.info('Refreshing cache for %s' % (website.name,))
        cache_website(website, get_website_redis_key(website.token), redis)
    else:
        logging.info('Up to date: %s' % (website.name,))


def process_website_updates():
    redis = get_redis(backup=True)
    websites = []
    list_key = get_website_refresh_redis_key()
    done = False
    while not done:
        website_id = redis.rpop(list_key)
        if website_id:
            websites.append(Website.objects.get(id=website_id))
        else:
            done = True
    logging.info('%s website updates to process' % len(websites))
    for backup in [True, False]:
        redis = get_redis(backup=backup)
        for website in websites:
            logging.info('Refresh cache for %s on %s redis' % (website.name, 'backup' if backup else 'standard'))
            _refresh_cache_for_website(website, redis)
            logging.info('Refreshed cache for %s on %s redis' % (website.name, 'backup' if backup else 'standard'))

def queue_website_update(website):
    redis = get_redis(backup=True)
    redis.lpush(get_website_refresh_redis_key(), website.id)

def _process_page_views(backup_key='lst:pageviews:backup', list_key=None):
    pvrs = []
    for backup in [True, False]:
        redis = get_redis(backup=backup)
        done = False
        while not done:
            if list_key:
                pickled_pvr = redis.rpoplpush(list_key, backup_key)
            else:
                pickled_pvr = redis.rpop(backup_key)
            pvr = pickle.loads(pickled_pvr) if pickled_pvr else None
            if pvr:
                if save_page_view_to_db(pvr):
                    logging.info('Saved pvr for %s, uid: %s' % (pvr['token'], pvr['uid']))
                    pvrs.append(pvr)    
            else:
                done = True
    return pvrs

def process_page_views():
    pvrs = _process_page_views(list_key=get_pageview_redis_key())
    #now populate the reporting redis
    redis = get_redis(backup=True)
    for pvr in pvrs:
        for f_id in pvr['filters']:
            redis.incr(get_filter_hits_redis_key(pvr['token'], f_id)
                       , 1)
            redis.incr(get_filter_hits_by_month_redis_key(pvr['token'], f_id, pvr['view_date'])
                       , 1)
            redis.incr(get_filter_hits_by_day_redis_key(pvr['token'], f_id, pvr['view_date'])
                       , 1)

def process_backup_page_views():
    _process_page_views()
    
    
     

#############
# Reporting stuff
# use backup redis
#############
def get_filter_hits(website_token, days=14):

    redis = get_redis(backup=True)
    website = Website.objects.get(token=website_token)
    today = datetime.date.today()
    filter_hits = {}
    for filter in website.filters.all():
        filter_hits[filter.id] = []
        if redis.get(get_filter_hits_redis_key(website_token, filter.id)) != None: #good indication that data is loaded    
            for i in range(days-1, -1, -1):
                result = redis.get(get_filter_hits_by_day_redis_key(website_token, filter.id, today - datetime.timedelta(days=i))) or 0
                filter_hits[filter.id].append(int(result))
        else:
            ffrs = FilterFiredRecord.objects.select_related().filter(filter_id=filter.id, page_view__website_token=website_token, page_view__view_date__gte=today-datetime.timedelta(days=days-1))
            aggregate = {}
            for ffr in ffrs:
                day = (today - ffr.page_view.view_date.date()).days
                count = aggregate.get(day, 0) + 1
                aggregate[day] = count
            for i in range(days-1, -1, -1):
                hits = aggregate.get(i, 0)
                filter_hits[filter.id].append(hits)
                fhit_key = get_filter_hits_by_day_redis_key(website_token, filter.id, today - datetime.timedelta(days=i))
                redis.set(fhit_key, hits)
                redis.expire(fhit_key, 86400 * (days + 1 - i))
            redis.set(get_filter_hits_redis_key(website_token, filter.id), FilterFiredRecord.objects.filter(filter_id=filter.id, page_view__website_token=website_token).count())
            
    return filter_hits

