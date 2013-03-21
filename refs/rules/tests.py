from django.test import TestCase
from refs.rules.models import SearchTermHandler, LocationHandler, \
    LocationGroup, Country, ReferralHandler, Website, FrequentVisitorHandler,\
    QueryStringHandler, TimeHandler, Filter, PageGroup, Page, ChangeHistory,\
    ChangedValue
from django.http import HttpRequest
from pytz import timezone, utc
from django.contrib.gis.utils.geoip import GeoIP
from redis import Redis
import datetime
import time
import urllib
from refs.landing.models import PageViewRecord, Url, ClientVisitStart
import logging
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.contenttypes.models import ContentType
from refs.utils import get_visits_redis_key

class TestFilter(TestCase):
    def setUp(self):
        self.website = Website.objects.all()[0]
    
    def test_general(self):
        f = Filter(website=self.website, name='test', html="<h1>hit</h1>")
        f.save()
        
        thandler = TimeHandler(timezone="UTC")
        thandler.save()
        shandler = SearchTermHandler(search_terms='frank')
        shandler.save()
        f.rules.create(website=self.website, name='rule 1', handler_choice=30, handler=shandler)
        f.rules.create(website=self.website, name='rule 2', handler_choice=50, handler=thandler)
        
        filter = Filter.objects.get(id=f.id)
        
        req = HttpRequest()
        self.assertFalse(filter.check(req)) #no search terms
        
        req.GET = {'r': urllib.quote_plus('http://www.google.com/?q=daisy+frank+harry')}
        self.assertTrue(filter.check(req))
        
        pg = PageGroup(website=self.website, name='pg 1')
        pg.save()
        Page(page_group=pg, url='/bobspage/index.html').save()
        Page(page_group=pg, url='/product/*/spec.html').save()
        Page(page_group=pg, url='/spage/?x=y').save()
        Page(page_group=pg, url='/spage/?z=*').save()
        Page(page_group=pg, url='/').save()
        
        filter.page_group = pg
        filter.all_pages = 0
        filter.save()
        
        filter = Filter.objects.get(id=filter.id)
        
        for loc, result in [('http://www.example.com/index.html', True),
                            ('http://www.example.com/bobspage/index.html', True),
                            ('http://www.example.com/product/doodad/spec.html', True),
                            ('http://www.example.com/spage/index.html?x=y', True),
                            ('http://www.example.com/', True),
                            ('http://www.example.com/spage/index.html?z=2312&dsfsd=sdf', True),
                            ('http://www.example.com/gsdf?x=y', False),
                            ('http://www.example.com/bobspage/', False)]:
            req.GET['l'] = loc
            self.assertTrue(result == filter.check(req), msg='%s expected to return %s' % (loc, result)) 

#    def test_no_db_queries(self):             
        
        
        
        

class TestFrequentVisitorHandler(TestCase):
    def setUp(self):
        if not hasattr(self, 'redis'):
            self.redis = Redis(db=9)
        self.redis.flushdb()
        self.website = Website.objects.all()[0]
        
        self.cid1 = '123456789012'
        self.cid2 = '987654123457'
        self.cid3 = 'dsfsdfsd'
        
        self.dummy_url = Url(url='http://www.example.com/')
        self.dummy_url.save()

    def tearDown(self):
        self.redis.connection.disconnect()
    
    def test_general(self):
        handler = FrequentVisitorHandler(visit_count=3, time_frame=14, more_or_less=1)
        
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        
        req.GET = {'t': self.website.token}
        self.assertFalse(handler.check(req))
        
        for c in [None, 
                  '',
                  'garbage']:
            req.GET['c'] = c
            self.assertFalse(handler.check(req))
        
        req.redis = self.redis
        for c in [None, 
                  '',
                  'garbage']:
            req.GET['c'] = c
            self.assertFalse(handler.check(req))


    def _more_than_2(self, req, handler):
        now = datetime.datetime.now()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid1, 
                         visit_date=now - datetime.timedelta(days=16)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid1, 
                         visit_date=now - datetime.timedelta(days=15)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid1, 
                         visit_date=now - datetime.timedelta(days=14) + datetime.timedelta(seconds=3605)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid1, 
                         visit_date=now - datetime.timedelta(days=12)).save()
        self.assertFalse(handler.check(req))
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid1, 
                         visit_date=now - datetime.timedelta(days=11)).save()
        self.assertTrue(handler.check(req))
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid1, 
                         visit_date=now - datetime.timedelta(days=1)).save()
        self.assertTrue(handler.check(req))
    
    def _less_than_4(self, req, handler):
        now = datetime.datetime.now()
        self.assertTrue(handler.check(req))
        self.redis.flushdb()
            
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2, 
                         visit_date=now - datetime.timedelta(days=15)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2, 
                         visit_date=now - datetime.timedelta(days=12)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2, 
                         visit_date=now - datetime.timedelta(days=17)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2, 
                         visit_date=now - datetime.timedelta(days=18)).save()
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2,
                         visit_date=now - datetime.timedelta(days=14) + datetime.timedelta(seconds=3605)).save()
        
        self.assertTrue(handler.check(req)) #2 visits under the 14 days... 
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2, 
                         visit_date=now - datetime.timedelta(days=2)).save()
        self.assertTrue(handler.check(req)) #3 visits under the 14 days...
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid2, 
                       visit_date=now - datetime.timedelta(days=7)).save()
        self.assertFalse(handler.check(req))
        
    
    def _unlimited_time(self, request):
        handler_more = FrequentVisitorHandler(visit_count=2, time_frame=0, more_or_less=1)
        handler_less = FrequentVisitorHandler(visit_count=3, time_frame=0, more_or_less=2)
        
        self.assertFalse(handler_more.check(request))
        self.assertTrue(handler_less.check(request))
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid3, 
                         visit_date=datetime.datetime(2005,11,1,12,11,29)).save()
        self.assertFalse(handler_more.check(request))
        self.assertTrue(handler_less.check(request))
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid3, 
                         visit_date=datetime.datetime(2008,4,25,3,11,59)).save()
        self.assertTrue(handler_more.check(request))
        self.assertTrue(handler_less.check(request))
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid3, 
                         visit_date=datetime.datetime(2002,1,12,4,11,36)).save()
        self.assertTrue(handler_more.check(request))
        self.assertFalse(handler_less.check(request))
        self.redis.flushdb()
        
        ClientVisitStart(website_token=self.website.token, client_identifier=self.cid3, 
                       visit_date=datetime.datetime(2010,1,12,4,11,36)).save()
        self.assertTrue(handler_more.check(request))
        self.assertFalse(handler_less.check(request))
        
             
    def test_non_redis(self):
        handler = FrequentVisitorHandler(visit_count=3, time_frame=14, more_or_less=1)
        req = HttpRequest()
        req.GET = {'t': self.website.token, 'c': self.cid1}
        
        self._more_than_2(req, handler)
        
        handler = FrequentVisitorHandler(visit_count=4, time_frame=14, more_or_less=2)
        req.GET['c'] = self.cid2
        self._less_than_4(req, handler)
        
        req.GET['c'] = self.cid3
        self._unlimited_time(req)
        
    
    def test_redis(self):
        handler = FrequentVisitorHandler(visit_count=3, time_frame=14, more_or_less=1)
        
        req = HttpRequest()
        req.GET = {'t': self.website.token, 'c': self.cid1}
        req.redis = self.redis
        
        self._more_than_2(req, handler)
        
        #now if we delete the DB objects, it should still work as the data should be in redis
        ClientVisitStart.objects.all().delete()
        logging.debug('True? %s' % handler.check(req))

        self.assertTrue(handler.check(req))
        
        handler = FrequentVisitorHandler(visit_count=4, time_frame=14, more_or_less=2)
        req.GET['c'] = self.cid2
        self._less_than_4(req, handler)

        ClientVisitStart.objects.all().delete()
        logging.debug('False? %s' % handler.check(req))
        self.assertFalse(handler.check(req))
        
        req.GET['c'] = self.cid3
        self._unlimited_time(req)
    
    def test_redis_ztime(self):
        handler = FrequentVisitorHandler(visit_count=1, time_frame=14, more_or_less=1)
        
        req = HttpRequest()
        req.GET = {'t': self.website.token, 'c': self.cid1}
        req.redis = self.redis
        
        zkey = get_visits_redis_key(self.website.token, self.cid1)
        other_side_of_fourteen = time.time() - (86400*14) - 3
        self.redis.zadd(zkey, other_side_of_fourteen, other_side_of_fourteen)
        
        self.assertFalse(handler.check(req))
        self.redis.flushdb()
        
        this_side_of_fourteen = time.time() - (86400*14) + 3
        self.redis.zadd(zkey, this_side_of_fourteen, this_side_of_fourteen)
        
        self.assertTrue(handler.check(req))
        
        

class TestReferralHandler(TestCase):    
    def test_general(self):
        handler = ReferralHandler(url='http://www.example.com')
        handler.prepare()
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        
        for u, result in [(None, False),
                          ('', False),
                          ('http://www.example.com', True),
                          ('http://www.example.com/some_other_folder/index.html', True),
                          ('http://www.exAMPle.com', True),
                          ('http://www.example.co', False),
                          ]:
            req.GET = {'r': urllib.quote_plus(u) if u else None}
            self.assertTrue(handler.check(req) == result, msg='%s should have returned %s' % (u, result))
        
        handler = ReferralHandler(url='http://www.example.com/ad_result/landing.html')
        handler.prepare()
        
        for u, result in [('http://www.example.com', False),
                          ('http://www.example.com/ad_result/landing.html', True),
                          ('http://www.example.com/ad_result/landing.html?gclid=ssdafasefdDFGD3f', True),
                          ]:
            req.GET = {'r': urllib.quote_plus(u) if u else None}
            self.assertTrue(handler.check(req) == result, msg='%s should have returned %s' % (u, result))
    
    
class TestSearchTermsHandler(TestCase):
    def test_non_google(self):
        pass

    def test_general(self):
        """
        Tests the basics: missing referrer, query string etc. 
        """
        handler = SearchTermHandler(search_terms='alice')
        handler.prepare()
        
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        
        for ref, result in [
                            ('http://www.google.co.uk/search?not_the_right_param=alice', False),
                            ('gibberish', False),
                            ('', False),
                            ('http://www.example.com/no_query_string/', False),
                            ]:
            req.GET = {'r': urllib.quote_plus(ref)}
            self.assertTrue(result == handler.check(req), msg='%s should have tested %s' % (ref, result))
        
        #check wildcards aren't possible
        handler = SearchTermHandler(search_terms='b*ob frank')
        handler.prepare()
        
        for t, result in [  ('baaaaob', False),
                            ('bbbbbbob', False),
                            ]:
            req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=' + t)}
            self.assertTrue(result == handler.check(req), msg='%s should have tested %s' % (t, result))        
        
        
    def test_whole_phrase(self):
        """
        Tests the case where we're trying to match the exact phrase 
        """
        handler = SearchTermHandler(search_terms='"alice bob carol"')
        handler.prepare()
        
        req = HttpRequest()
        for t in ['alice+bob+carol',
                  '+alice+bob+carol+',
                  '   alice  bob   carol',
                  'Alice+BOB+caROl',
                  '+aliCE+bob++caroL+',
                  ' dave alice bob carol frank smith']:
            req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=%s' % (t))}
            self.assertTrue(handler.check(req), msg='%s should have tested TRUE' % t)
        
        for t in ['alicebob+carol',
                  '+alice+bob+caro',
                  ' alice  .*   carol',
                  'Alicee+BOB+caROl',]:
            req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=%s' % (t))}
            self.assertFalse(handler.check(req), msg='%s should have tested FALSE' % t)

    def test_mixed(self):
        handler = SearchTermHandler(search_terms='alice "frank smith" dave')
        handler.prepare()
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        for t, result in [  ('sandra frank smith bob', True),
                            ('crazy dave crank', True),
                            ('frank smith', True),
                            ('alice', True),
                            ('frank alice', True),
                            ('smith dave', True),
                            ('  frank   smith  ', True),
                            (' frank   smith ', True),
                            ('frank dull smith', False),
                            ('frank crank', False),
                            ('darryl smith', False),
                            ]:
            req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=' + t)}
            self.assertTrue(result == handler.check(req), msg='%s should have tested %s' % (t, result))
        
        handler = SearchTermHandler(search_terms=' "frank smith" alice  dave')
        handler.prepare()
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        for t, result in [  ('sandra frank smith bob', True),
                            ('crazy dave crank', True),
                            ('frank smith', True),
                            ('alice', True),
                            ('frank alice', True),
                            ('smith dave', True),
                            ('  frank   smith  ', True),
                            (' frank   smith ', True),
                            ('frank dull smith', False),
                            ('frank crank', False),
                            ('darryl smith', False),
                            ]:
            req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=' + t)}
            self.assertTrue(result == handler.check(req), msg='%s should have tested %s' % (t, result))
        
        handler = SearchTermHandler(search_terms='dave "don\'t be silly" fgs')
        handler.prepare()
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        for t, result in [  ('don\'t be silly', True),
                            ]:
            req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=' + t)}
            self.assertTrue(result == handler.check(req), msg='%s should have tested %s' % (t, result))
        
    
    def test_any_word(self):
        """
        Tests the case where we're trying to match any word 
        """
        handler = SearchTermHandler(search_terms='alice bob carol')
        handler.prepare()
        
        req = HttpRequest()
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice+bob+carol')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=+alice')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=+alice+')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice+')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice')}
        self.assertTrue(handler.check(req))        
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice+++')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice+carol')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice++carol')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alice+bob')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=+carol')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=+carol+')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=carol+')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=+bob')}
        self.assertTrue(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=+bob+')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=bob+')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=bob')}
        self.assertTrue(handler.check(req))

        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=alicebob')}
        self.assertFalse(handler.check(req))
        
        req.GET = {'r': urllib.quote_plus('http://www.google.co.uk/search?q=')}
        self.assertFalse(handler.check(req))


class TestLocationHandler(TestCase):
    def test_general(self):
        us = Country.objects.get(code='US')
        us_group = LocationGroup(name='US-CA/NY')
        us_group.save()
        us_group.locations.create(country=us, us_state='CA')
        us_group.locations.create(country=us, us_state='NY')
        handler = LocationHandler()
        handler.save()
        handler.location_groups.add(us_group)
        handler.prepare()
        
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        geo = GeoIP()

        for ip, result in [('', False ),
                           ('127.0.0.1', False),
                           ('212.58.244.70', False), #bbc
                           ('173.194.37.104', True), #google, CA
                           ('207.17.33.246', True), #gs, NY?
                           ('72.32.191.88', False), #rackspace, TX?
                           ]:
            req.META = {'REMOTE_ADDR': ip }
            self.assertTrue(handler.check(req) == result, msg='%s expected to return %s (%s)' % (ip, result, geo.city(ip)))
        
        uk_group = LocationGroup(name='UK')
        uk_group.save()
        uk_group.locations.create(country=Country.objects.get(code='GB'))
        
        handler = LocationHandler()
        handler.save()
        handler.location_groups.add(us_group)
        handler.location_groups.add(uk_group)
        handler.prepare()
        
        for ip, result in [('212.58.244.70', True), #bbc
                           ('173.194.37.104', True), #google, CA
                           ('207.17.33.246', True), #gs, NY?
                           ('72.32.191.88', False), #rackspace, TX?
                           ]:
            req.META = {'HTTP_X_FORWARDED_FOR': ip }
            self.assertTrue(handler.check(req) == result,  msg='%s expected to return %s (%s)' % (ip, result, geo.city(ip)))
        
        handler_gb = LocationHandler()
        handler_gb.save()
        handler_gb.location_groups.add(uk_group)
        handler_gb.prepare()
        
        for ip, result in [('212.58.244.70', True), #bbc
                           ('173.194.37.104', False), #google, CA
                           ('207.17.33.246', False), #gs, NY?
                           ('72.32.191.88', False), #rackspace, TX?
                           ]:
            req.META = {'REMOTE_ADDR': ip }
            self.assertTrue(handler_gb.check(req) == result,  msg='%s expected to return %s (%s)' % (ip, result, geo.city(ip)))
        
        us_all = LocationGroup(name='US-ALL')
        us_all.save()
        us_all.locations.create(country=us)
        
        handler = LocationHandler()
        handler.save()
        handler.location_groups.add(us_all)
        handler.prepare()
        
        for ip, result in [('212.58.244.70', False), #bbc
                           ('173.194.37.104', True), #google, CA
                           ('207.17.33.246', True), #gs, NY?
                           ('72.32.191.88', True), #rackspace, TX?
                           ]:
            req.META = {'REMOTE_ADDR': ip }
            self.assertTrue(handler.check(req) == result, msg='%s expected to return %s (%s)' % (ip, result, geo.city(ip)))
        
        
class TestTimeHandler(TestCase):        
    def test_date_general(self):
        utc = "UTC"
        
        handler = TimeHandler(timezone=utc, date_from=None, date_to=datetime.date(2014,9,1))    
        self.assertTrue(handler.check(None))
        handler = TimeHandler(timezone=utc, date_to=None, date_from=datetime.date(2010,6,1))
        self.assertTrue(handler.check(None))
        handler = TimeHandler(timezone=utc, date_to=None, date_from=datetime.date(2014,6,1))
        self.assertFalse(handler.check(None))
        handler = TimeHandler(timezone=utc, date_from=None, date_to=datetime.date(2010,6,1))
        self.assertFalse(handler.check(None))
        
        today = datetime.date.today()
        handler = TimeHandler(timezone=utc, date_from=None, date_to=today)
        self.assertTrue(handler.check(None)) # inclusive
        handler = TimeHandler(timezone=utc, date_to=None, date_from=today)
        self.assertTrue(handler.check(None)) # inclusive
        
        
    def test_date_comparisons(self):
        eur_lon = "Europe/London" # DST
        us_est = "US/Eastern" # DST
        am_phx = "America/Phoenix" # no DST

        print '--------\n', 'EUR_LON\n', '---------\n'
        handler = TimeHandler(timezone=eur_lon, date_from=datetime.date(2012, 7, 9), date_to=datetime.date(2012, 7, 9))
        tz = timezone(eur_lon)
        kwargs = {'tzinfo': utc}
        for t in ((2012, 7, 8, 23, 1),
                  (2012, 7, 9, 22, 59),
                  (2012, 7, 9, 12, 11),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertTrue(handler.compare_dates(tz_now, tz))
        for t in ((2012, 7, 8, 22, 59),
                  (2012, 7, 9, 23, 1),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertFalse(handler.compare_dates(tz_now, tz))
            
        handler = TimeHandler(timezone=eur_lon, date_from=datetime.date(2012, 1, 9), date_to=datetime.date(2012, 1, 9))
        for t in ((2012, 1, 9, 0, 1),
                  (2012, 1, 9, 23, 59),
                  (2012, 1, 9, 12, 11),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertTrue(handler.compare_dates(tz_now, tz))
        for t in ((2012, 1, 8, 23, 59),
                  (2012, 1, 10, 0, 1),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertFalse(handler.compare_dates(tz_now, tz))
        
        print '--------\n', 'US_EST\n', '---------\n'
        tz = timezone(us_est)
        handler = TimeHandler(timezone=us_est, date_from=datetime.date(2012, 1, 9), date_to=datetime.date(2012, 1, 9))
        for t in ((2012, 1, 9, 5, 0),
                  (2012, 1, 10, 4, 59),
                  (2012, 1, 9, 12, 11),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertTrue(handler.compare_dates(tz_now, tz), msg='tz_now: %s should have tested TRUE' % tz_now)
        for t in ((2012, 1, 9, 4, 59),
                  (2012, 1, 10, 5, 0),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertFalse(handler.compare_dates(tz_now, tz))
            
        handler = TimeHandler(timezone=us_est, date_from=datetime.date(2012, 7, 9), date_to=datetime.date(2012, 7, 9))
        for t in ((2012, 7, 9, 4, 0),
                  (2012, 7, 10, 3, 59),
                  (2012, 7, 9, 12, 11),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertTrue(handler.compare_dates(tz_now, tz), msg='tz_now: %s should have tested TRUE' % tz_now)
        for t in ((2012, 7, 9, 3, 59),
                  (2012, 7, 10, 4, 0),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertFalse(handler.compare_dates(tz_now, tz))
               
        print '--------\n', 'AM_PHX\n', '---------\n'
        tz = timezone(am_phx)
        handler = TimeHandler(timezone=am_phx, date_from=datetime.date(2012, 1, 9), date_to=datetime.date(2012, 1, 9))
        for t in ((2012, 1, 9, 7, 0),
                  (2012, 1, 10, 6, 59),
                  (2012, 1, 9, 12, 11),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertTrue(handler.compare_dates(tz_now, tz), msg='tz_now: %s should have tested TRUE' % tz_now)
        for t in ((2012, 1, 9, 6, 59),
                  (2012, 1, 10, 7, 0),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertFalse(handler.compare_dates(tz_now, tz))
            
        handler = TimeHandler(timezone=am_phx, date_from=datetime.date(2012, 7, 9), date_to=datetime.date(2012, 7, 9))
        for t in ((2012, 7, 9, 7, 0),
                  (2012, 7, 10, 6, 59),
                  (2012, 7, 9, 12, 11),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertTrue(handler.compare_dates(tz_now, tz), msg='tz_now: %s should have tested TRUE' % tz_now)
        for t in ((2012, 7, 9, 6, 59),
                  (2012, 7, 10, 7, 0),
                  ):
            tz_now = datetime.datetime(*t, **kwargs).astimezone(tz)
            self.assertFalse(handler.compare_dates(tz_now, tz))
    
    def test_weekday(self):
        utc = "UTC"
        wkdy = datetime.date.today().weekday()
        if wkdy == 0:
            handler = TimeHandler(timezone=utc, tuesday=False, wednesday=False, thursday=False, friday=False, saturday=False, sunday=False)
        elif wkdy == 1:
            handler = TimeHandler(timezone=utc, monday=False, wednesday=False, thursday=False, friday=False, saturday=False, sunday=False)
        elif wkdy == 2:
            handler = TimeHandler(timezone=utc, tuesday=False, monday=False, thursday=False, friday=False, saturday=False, sunday=False)
        elif wkdy == 3:
            handler = TimeHandler(timezone=utc, tuesday=False, wednesday=False, monday=False, friday=False, saturday=False, sunday=False)
        elif wkdy == 4:
            handler = TimeHandler(timezone=utc, tuesday=False, wednesday=False, thursday=False, monday=False, saturday=False, sunday=False)
        elif wkdy == 5:
            handler = TimeHandler(timezone=utc, tuesday=False, wednesday=False, thursday=False, friday=False, monday=False, sunday=False)
        elif wkdy == 6:
            handler = TimeHandler(timezone=utc, tuesday=False, wednesday=False, thursday=False, friday=False, saturday=False, monday=False)
                
        self.assertTrue(handler.check(None))
        
        kwargs = {datetime.date.today().strftime('%A').lower(): False}
        handler = TimeHandler(timezone=utc, **kwargs)
        self.assertFalse(handler.check(None))
        
    
class TestQueryStringHandler(TestCase):        
    def test_general(self):
        handler = QueryStringHandler(query_string='fish=chips')
        handler.prepare()
        
        req = HttpRequest()
        self.assertFalse(handler.check(req))
        
        req.GET = {'l': 'http://www.example.com/'}
        self.assertFalse(handler.check(req))
        
        for qs, result in [('', False ),
                           ('fish=chip', False),
                           ('ish=chips', False), 
                           ('some=2&fish=chips', True), 
                           ('fish=chips&bob=freddy', True), 
                           ('fish=chips', True),
                           ('fiSH=cHIps', True),
                           ('batteredfiSH=cHIpswithvinegar', True), 
                           ]:
            req.GET = {'l': 'http://www.example.com/?%s' % qs }
            self.assertTrue(handler.check(req) == result, msg='%s expected to return %s' % (qs, result))

#        handler = QueryStringHandler(query_string='(^|&)fish=chips($|&)')
#        handler.prepare()
#        
#        for qs, result in [('some=2&fish=chips', True), 
#                           ('fish=chips&bob=freddy', True), 
#                           ('fish=chips', True),
#                           ('bob=1&fiSH=cHIps&frank=3', True),
#                           ('batteredfiSH=cHIpswithvinegar', False), 
#                           ]:
#            req.GET = {'l': 'http://www.example.com/?%s' % qs }
#            self.assertTrue(handler.check(req) == result, msg='%s expected to return %s' % (qs, result)) 
        
        
class TestViews(TestCase):        
    
    def check_login_required(self, url, usernm='stevendavidson', passwd='a'):
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, '%s?next=%s' % (reverse('django.contrib.auth.views.login'), url), 302, 200)
        response = self.client.post(url, {'some_data': 'fred.com'}, follow=True)
        self.assertRedirects(response, '%s?next=%s' % (reverse('django.contrib.auth.views.login'), url), 302, 200)
        
        self.client.login(username=usernm, password=passwd)
    
    def test_add_website(self):
        self.assertEqual(ChangeHistory.objects.all().count(), 0)
        
        add_website_url = reverse('add_website')
        self.check_login_required(add_website_url)
        
        logging.debug('add website')
        response = self.client.post(add_website_url, {'name': 'fred.com', 'include_subdomains': True, 'ga_event_tracking': True, 'tracking_method': 'evt',}, follow=False)
        logging.debug('check response')
        self.assertEqual(response.status_code, 302)
        new_website = Website.objects.get(name='fred.com')
        
        self.assertEqual(ChangeHistory.objects.all().count(), 1)
        website_type = ContentType.objects.get_for_model(Website)
        self.assertTrue(ChangeHistory.objects.filter(object_id=new_website.id, content_type=website_type)[0].reason.startswith('++ CREATED ++'))
    
    def test_edit_website(self):
        self.assertEqual(ChangeHistory.objects.all().count(), 0)
        self.assertEqual(ChangedValue.objects.all().count(), 0)
        
        edit_website_url = reverse('edit_website', kwargs={'id': 1})
        self.check_login_required(edit_website_url)
        
        website = Website.objects.get(id=1)
        
        new_data = website.__dict__.copy()
        new_data['name'] = 'www.example.com'
        new_data['exact_match'] = 1
        
        response = self.client.post(edit_website_url, new_data, follow=False)
        self.assertEqual(response.status_code, 302)

        website_type = ContentType.objects.get_for_model(Website)        
        self.assertEqual(ChangeHistory.objects.filter(object_id=1, content_type=website_type).count(), 1)
        self.assertEqual(ChangedValue.objects.all().count(), 2)
        
        
        