"""
This file demonstrates two different styles of tests (one doctest and one
unittest). These will both pass when you run "manage.py test".

Replace these with more appropriate tests for your application.
"""

from django.test import TestCase
import urllib
from refs.rules.models import Website
from django.core.urlresolvers import reverse
from refs.landing.records import get_website_from_db, get_redis, cache_website,\
    get_website, switch_redis
import logging
from refs.utils import get_website_redis_key
from refs.settings import REDIS_URL
import redis
from redis.client import Redis

class TestLandingView(TestCase):
    urls = 'refs.landing.urls'
    
    def get_url(self, root, location, website=None, token=None, client='', referrer='', visit_start=''):
        return '%s?t=%s&l=%s&r=%s&c=%s&n=%s' % (root, 
                                                token or website.token, 
                                                urllib.quote_plus(location), 
                                                urllib.quote_plus(referrer),
                                                client,
                                                visit_start )
    
    def test_edit_website(self):
        msg_url = reverse('get_messages')
        website = Website.objects.get(id=1)
        logging.debug('website: %s' % website)
        url = self.get_url(msg_url, 'http://www.landing.at/marketing/', website)
        
        response = self.client.get(url, follow=False)
        self.assertEqual(response.status_code, 204)


class TestRecordMethods(TestCase):
    
    def test_get_website_from_db(self):
        website = Website.objects.all()[0]
        logging.debug('website from DB: %s' % website)
        
        website_from_method = get_website_from_db(website.token)
        logging.debug('website from method call: %s' % website_from_method)
        
        self.assertEqual(website, website_from_method)

    def test_get_website_from_redis(self):
        #clear redis
        redis = get_redis()
        redis.flushall()
        
        #store known website in redis
        website = Website.objects.all()[0]
        logging.debug('website from DB: %s' % website)
        website.prepare()
        website._special_attribute = 'special'
        
        cache_website(website, get_website_redis_key(website.token), redis)
        
        # retrieve via normal method
        website_from_method = get_website(website.token)
        
        self.assertEqual(website, website_from_method)
        self.assertTrue(hasattr(website_from_method, '_special_attribute') and website_from_method._special_attribute == 'special')
        
        #clear redis and store website in backup...
        redis.flushall()
        redis = switch_redis()
        website._special_attribute = 'special backup'
        
        cache_website(website, get_website_redis_key(website.token), redis)
        
        # be very clear that it's in the backup
        main_redis = redis.from_url(REDIS_URL) # Redis(**REDIS_DBS['default'])
        main_redis.flushdb()
        
        # retrieve via normal method
        website_from_method = get_website(website.token)
        
        self.assertEqual(website, website_from_method)
        self.assertTrue(hasattr(website_from_method, '_special_attribute') and website_from_method._special_attribute == 'special backup')
    



def timings():
    import timeit
    website = Website.objects.get(id=1)
    db_timer = timeit.Timer('gc.enable(); from refs.landing import records; records.get_website_from_db("%s")' % website.token)
    logging.info(db_timer.timeit(number=10000))
    redis_timer = timeit.Timer('gc.enable(); from refs.landing import records; records.get_website("%s")' % website.token)
    logging.info(redis_timer.timeit(number=10000))
    
        
        
        
