from django.db import models
from django.contrib.auth.models import User
from django import forms
from django.forms.models import inlineformset_factory
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from urlparse import urlparse
from refs.rules.tz import TZ_CHOICES
from refs.utils import random_token, format_exception_info, get_visits_redis_key,\
    get_client_ip
from cgi import parse_qs
#from django.contrib.gis.utils.geoip import GeoIP
from pytz import timezone, utc
import time
import urllib
import re
import datetime
import uuid
import logging
from django.core.mail import mail_admins
from django.db.utils import DatabaseError
from django.core.validators import RegexValidator
from django.forms.util import ErrorList
from django.forms.widgets import Textarea
from refs.accounts.models import Account, Country



def strip_chars(self, value):
    value = self._mprd_to_python(value)
    return value.strip()

#Monkey patch CharField
from django.forms.fields import CharField
if not hasattr(CharField, '_mprd_to_python'):
    CharField._mprd_to_python = CharField.to_python
    CharField.to_python = strip_chars


READ_ONLY = 10
RULE_EDIT = 20
ADMIN = 30

ACCESS_LEVEL = (
            (READ_ONLY, 'Read-only User'),
            (RULE_EDIT, 'Profile Editor'),
            (ADMIN, 'Administrator'),
)

HANDLER_CHOICES_DICT = {
    10: 'Referring Page',
    20: 'Campaign',
    30: 'Search Terms',
    50: 'Time & Date',
    60: 'Location',
    70: 'Frequent Visitor',
}

ONE_RULE_ONLY = (10, 50, 60,)

HANDLER_CHOICES = (('', 'Please select'),) + tuple([(k,HANDLER_CHOICES_DICT[k]) for k in sorted(HANDLER_CHOICES_DICT.keys())])

MORE_OR_LESS_CHOICES = (
            (1, 'at least'),
            (2, 'fewer than'),
)

ALL_PAGES = 1
SPECIFIC_PAGES = 0
PAGE_CHOICE = (
               (ALL_PAGES, 'All pages'),
               (SPECIFIC_PAGES, 'Specific page(s)'),
)

TRACKING_CHOICES = (
        ('non', 'None'),
        ('evt', 'Event'),
        ('vpv', 'Virtual pageview'),
        ('cvr', 'Custom variables'),
)

LIBRARY_CHOICES = (
        ('non', 'None'),
        ('jqy', 'jQuery 1.2+'),
        ('moo', 'MooTools'),
)

TRANSITION_CHOICES = (
        ('non', 'None'),
        ('dft', 'Default'),
)

website_name_re = re.compile(r'^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}$', re.IGNORECASE) 
validate_website_name = RegexValidator(website_name_re, u"Enter a valid host name consisting of letters, numbers, '-', '.' only. e.g. example.com", 'invalid')

element_id_re = re.compile(r'^[A-Z](?:[A-Z0-9_:.-]+)?$', re.IGNORECASE)
element_id_validator = RegexValidator(element_id_re, u"Enter a valid id: must start with a letter optionally followed by letters, numbers, '-', '_', ':' or '.'. e.g. landingAtId1", 'invalid')

sanitizer_star_wildcard = re.compile(r'\\\*')

def make_string_safe_for_regex(unsafe_string):
    return sanitizer_star_wildcard.sub('.*', re.escape(unsafe_string))


class AuditMixin():
    def audit_simple_change(self, change, user):
        try:
            audit = ChangeHistory(changed_obj=self, changed_by=user, reason=(change)[:100])
            audit.save()
        except:
            exc = format_exception_info()
            mail_admins('audit failure', 'failed to audit change: %s\n\n%s\n\n%s' % (change, self, exc), fail_silently=True)
        
    def audit_update(self, old_obj_audit, user):
        try:
            diff = self.diff(old_obj_audit)
            if len(diff) > 0:
                audit = ChangeHistory(changed_obj=self, changed_by=user, reason='updated')
                audit.save()
                
                for fld, change in diff.items():
                    if isinstance(change, list):
                        for c in change:
                            ChangedValue(history=audit, field=fld, new_value=c[0], old_value=c[1]).save()
                    else:
                        ChangedValue(history=audit, field=fld, new_value=change[0], old_value=change[1]).save()
        except:
            exc = format_exception_info()
            logging.error(exc)
            mail_admins('audit failure', 'failed to audit update:\n\n%s\n\n%s\n\n%s' % (self, old_obj_audit, exc), fail_silently=True)
    
    def audit_fields(self):
        raise NotImplementedError()
    
    def diff(self, other_obj):
        raise NotImplementedError()

class PrepareMixin():
    def prepare(self):
        self._is_prepared = True
    
    def is_prepared(self):
        return getattr(self, '_is_prepared', False)

class ChangeHistory(models.Model):
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    changed_obj = generic.GenericForeignKey()

    changed_by = models.ForeignKey(User)
    changed_date = models.DateTimeField(auto_now_add=True, db_index=True)
    
    reason = models.CharField(max_length=100)

    def __unicode__(self):
        return '%s: %s changed by %s on %s. Change: %s' % (self.content_type.name, self.changed_obj, 
                                                    self.changed_by.email, self.changed_date,
                                                    self.reason)
    class Meta:
        ordering = ['-changed_date']
        verbose_name_plural = 'Change history'

class ChangedValue(models.Model):
    history = models.ForeignKey(ChangeHistory, related_name='changes')
    field = models.CharField(max_length=50)
    new_value = models.TextField()
    old_value = models.TextField()

    def __unicode__(self):
        return '%s-- new value: [%s]; was: [%s]' % (self.field, self.new_value, self.old_value)
    
    class Meta:
        ordering = ['field', 'new_value']

# Create your models here.
class Website(models.Model, AuditMixin, PrepareMixin):
    account = models.ForeignKey(Account, related_name='websites')
    name = models.CharField(max_length=255, validators=[validate_website_name], verbose_name="Website")
    exact_match = models.BooleanField(default=False)
    token = models.CharField(max_length=40, default=random_token, unique=True, db_index=True)
    active = models.BooleanField(default=True)
    url_wildcard = models.CharField(max_length=3, default='*')
    tracking_method = models.CharField(max_length=3, choices=TRACKING_CHOICES, default='evt')
    js_library = models.CharField(max_length=3, choices=LIBRARY_CHOICES)
    transition_type = models.CharField(max_length=3, choices=TRANSITION_CHOICES)
    
    verify_url = models.CharField(max_length=2048, blank=True)
    verified_date = models.DateTimeField(null=True, blank=True)
    
    deleted = models.BooleanField(default=False)

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    redis_db = models.CharField(max_length=30, default='default')
    
    def __init__(self, *args, **kwargs):
        super(Website, self).__init__(*args, **kwargs)
    
    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        super(Website, self).save(*args, **kwargs)
        
        from refs.landing.records import queue_website_update
        queue_website_update(self)
        
    def prepare(self):
        if not self.is_prepared():
            self._filters = []
            for filter in self.filters.filter(active=True, deleted=False).order_by('container_element_id', 'order'):
                self._filters.append(filter)
            super(Website, self).prepare()

    def check_filters(self, request):
        self.prepare()
        container = ''
        match = False
        filters = []
        for filter in self._filters:
            if match and container == filter.container_element_id:
                continue
            match = False
            if filter.check(request):
                filters.append(filter)
                match = True
                container = filter.container_element_id
        return filters

    def js_fragment(self):
        return render_to_string('rules/websites/javascript_fragment.html', {'website': self})
    
    def audit_fields(self):
        result = {'name': self.name,
                'exact match': self.exact_match,
                'active': self.active,
                'deleted': self.deleted,
                'invites': {},
                'website users': {}}
        
        for wuser in self.authorised_users.all():
            result['website users'][wuser.user.email] = {'level': wuser.get_level_display(),}
        
        for invite in self.invites.all():
            result['invites'][invite.email] = {'level': invite.get_level_display(),}
        
        return result
    
    def diff(self, other_obj):
        result = {}
        this_obj = self.audit_fields()
        
        for dk in ['invites', 'website users']:
            this_dict = this_obj[dk]
            other_dict = other_obj[dk]
            
            for k, v in this_dict.items():
                if not k in other_dict:
                    result['%s added' % (dk[:-1])] = tuple(['%s with permission %s' % (k, v['level']), '-'])
                elif v['level'] != other_dict[k]['level']:
                    result['%s changed' % (dk[:-1])] = tuple(['%s with permission %s' % (k, v['level']), '%s with permission %s' % (k, other_dict[k]['level'])])
            
            for k_old, v_old in other_dict.items():
                if not k_old in this_dict:
                    result['%s removed' % (dk[:-1])] = tuple(['-', '%s with permission %s' % (k_old, v_old['level'])])
            
            del this_obj[dk]
        
        for k, v in this_obj.items():
            if other_obj[k] != v:
                result[k] = tuple([v, other_obj[k]])
                 
        return result

def str_uuid():
    return str(uuid.uuid4())

class UserInvite(models.Model):
    email = models.EmailField()
    website = models.ForeignKey(Website, related_name='invites')
    level = models.IntegerField(choices=ACCESS_LEVEL, verbose_name="Role")
    token = models.CharField(max_length=40, default=str_uuid)
    email_sent = models.BooleanField(default=False)

    def __unicode__(self):
        return 'Invite for %s to %s with permission %s' % (self.email, self.website, self.get_level_display())

class WebsiteUser(models.Model):
    website = models.ForeignKey(Website, related_name='authorised_users')
    user = models.ForeignKey(User, related_name='authorised_websites')
    level = models.IntegerField(choices=ACCESS_LEVEL)

    def __unicode__(self):
        return '%s is %s on %s' % (self.user.email, self.get_level_display(), self.website)

    class Meta:
        ordering = ['website', 'level']
        

class PageGroup(models.Model):
    website = models.ForeignKey(Website, related_name='page_groups')
    name = models.CharField(max_length=200, blank=True)

    def __unicode__(self):
        return self.name

class Page(models.Model, PrepareMixin):
    page_group = models.ForeignKey(PageGroup, related_name='pages')
    url = models.CharField(max_length=2048, help_text='Can include * as a wildcard', verbose_name="URL")

    def __unicode__(self):
        return self.url

    class Meta:
        ordering = ['url']
    
    def prepare(self):
        if not self.is_prepared():
            if self.page_group.website.url_wildcard != '*':
                logging.error('Website wildcard is not "*" and no code has been written to handle this')
                raise RuntimeError('Website wildcard is not "*"') 
            
            default_files = '(index.html?|default.aspx?)?'
            
            url_pattern = make_string_safe_for_regex(self.url)
            q_mark = url_pattern.find('?') 
            if  q_mark > -1:
                self.include_query = True
                if url_pattern[q_mark-2] == "/":
                    url_pattern = r'%s%s%s' % ( url_pattern[:q_mark-1], default_files, url_pattern[q_mark-1:]) 
            else:
                self.include_query = False
                if url_pattern[-1] == '/': 
                    url_pattern = r'%s%s' % (url_pattern, default_files)
            url_pattern = '^%s$' % url_pattern
            self.regex = re.compile(url_pattern, re.IGNORECASE)
        super(Page, self).prepare()


class LocationGroup(models.Model):
    account = models.ForeignKey(Account, related_name='location_groups', blank=True, null=True)
    name = models.CharField(max_length=200)

    def __unicode__(self):
        return self.name
        
from django.contrib.localflavor.us import us_states

class Location(models.Model):
    location_group = models.ForeignKey(LocationGroup, related_name='locations')
    country = models.ForeignKey(Country)
    us_state = models.CharField(max_length=2, choices=us_states.STATE_CHOICES, blank=True)
    
    def __unicode__(self):
        if self.country.code == 'US' and self.us_state:
            return '%s, US' % self.get_us_state_display()
        return self.country.name

    class Meta:
        ordering = ['country', 'us_state']

class Rule(models.Model, AuditMixin):
    #account = models.ForeignKey(Account, related_name='rules')
    website = models.ForeignKey(Website, related_name='rules')
    name = models.CharField(max_length=200, blank=True)

    handler_choice = models.PositiveIntegerField(choices=HANDLER_CHOICES, verbose_name="Rule Type", default='')
    content_type = models.ForeignKey(ContentType, help_text='Content type must have a check method that takes a request object')
    object_id = models.PositiveIntegerField()
    handler = generic.GenericForeignKey()
    
    not_rule = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    
    updated_date = models.DateTimeField(auto_now=True) 
    copy_of = models.IntegerField(default=0)
    
    def __unicode__(self):
        return '%s%s' % ('NOT ' if self.not_rule else '', self.handler) 
    
    class Meta:
        ordering = ['handler_choice']

    def audit_fields(self):
        return  {'name': self.name,
                 'not rule': self.not_rule,
                 'deleted': self.deleted,
                 'h_choice': self.handler_choice,
                 'h_choice_display': self.get_handler_choice_display(), 
                 'repr': self.handler.full_repr(),
                 'copy of': self.copy_of}
    
    @staticmethod
    def static_diff(first_rule, second_rule):
        result = {}
        for k in ['name', 'not rule', 'deleted']:
            if first_rule[k] != second_rule[k]:
                result[k] = tuple([first_rule[k], second_rule[k]])
                
        if first_rule['repr'] != second_rule['repr']:
            type_changed = first_rule['h_choice'] != second_rule['h_choice']
            result['handler'] = tuple(['%s%s' % ('%s: ' % (first_rule['h_choice_display'] if type_changed else ''),
                                                          first_rule['repr']), 
                                                '%s%s' % ('%s: ' % (second_rule['h_choice_display'] if type_changed else ''),
                                                          second_rule['repr'])
                                                       ])
        return result


# define the Manager subclass.
class NonDeletedFilterManager(models.Manager):
    def get_query_set(self):
        return super(NonDeletedFilterManager, self).get_query_set().filter(deleted=False)

class Filter(models.Model, AuditMixin, PrepareMixin):
    website = models.ForeignKey(Website, related_name='filters')
    name = models.CharField(max_length=200)
    container_element_id = models.CharField(max_length=200, default='landingat1', validators=[element_id_validator], verbose_name="Profile Group ID")
    
    rules = models.ManyToManyField(Rule, related_name="filters")
    
    all_pages = models.IntegerField(choices=PAGE_CHOICE, default=ALL_PAGES, verbose_name='Apply Profile To')
    page_group = models.ForeignKey(PageGroup, related_name='filters', blank=True, null=True)
    
    html = models.TextField(verbose_name="Content", help_text="HTML")
    
    code = models.TextField(blank=True, help_text='Advanced use only!')
    a_b_testing_enabled = models.BooleanField(default=False, blank=True, 
                                              help_text='Create a control group by not showing activated filter messages to a small fraction of visitors')
    
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(blank=True, default=True)
    deleted = models.BooleanField(default=False, blank=True)        
    
    alert_schedule = models.ForeignKey('AlertSchedule', null=True, blank=True)
    
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    objects = NonDeletedFilterManager()
    all_objects = models.Manager()
    
    def __init__(self, *args, **kwargs):
        super(Filter, self).__init__(*args, **kwargs)
        if self.id:
            self.prepare()
    
    def __unicode__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        super(Filter, self).save(*args, **kwargs)
        self.website.save()
        
    class Meta:
        ordering = ['website', 'container_element_id', 'order']
        verbose_name = 'Profile'

    def audit_fields(self):
        result = {'name': self.name,
                'profile group ID': self.container_element_id,
                'all pages': True if self.all_pages == ALL_PAGES else False,
                'HTML': self.html,
                'code': self.code,
                'A/B test': self.a_b_testing_enabled,
                'rules': {},
                'order': self.order,
                'active': self.active,
                'deleted': self.deleted,}
        
        if self.all_pages == SPECIFIC_PAGES:
            result['pages'] = []
            for p in self.page_group.pages.all():
                result['pages'].append(p.url)
        
        for r in self.rules.all():
            result['rules'][r.id] = r.audit_fields()
        
        return result

    def diff(self, other_obj):
        diff = {}
        this_obj = self.audit_fields()
        for fld, val in this_obj.items():
            if fld == 'rules':
                other_rules = other_obj['rules']
                copied_rules = {}
                for rid, ruled in val.items():
                    if rid in other_rules or ruled['copy of'] in other_rules:
                        if rid in other_rules:
                            other_rule = other_rules[rid] 
                        else: 
                            copy_of = ruled['copy of']
                            other_rule = other_rules[copy_of]
                            copied_rules[copy_of] = copy_of
                        for rule_field, t in Rule.static_diff(ruled, other_rule).items():
                            diff['rule #%s (%s)' % (rid, rule_field)] = t
                    else:
                        diff['rule #%s' % rid] = tuple([ruled['repr'], 'n/a: created'])
                for oldrid, oldhandler in other_rules.items():
                    if oldrid not in val and oldrid not in copied_rules:
                        diff['rule #%s' % oldrid] = tuple(['n/a: deleted', oldhandler['repr']])
            elif fld == 'pages':
                oldpages = other_obj['pages'] if 'pages' in other_obj else []
                diff['added pages'] = []
                diff['deleted pages'] = []
                for u in val:
                    if not u in oldpages:
                        diff['added pages'].append(tuple([u, '-']))
                for u in oldpages:
                    if not u in val:
                        diff['deleted pages'].append(tuple(['-', u]))
            elif other_obj.get(fld, None) != val:
                diff[fld] = tuple([val, other_obj.get(fld, None)])

        if not 'pages' in this_obj and 'pages' in other_obj:
            diff['deleted pages'] = []
            for u in other_obj['pages']:
                diff['deleted pages'].append(tuple(['-', u]))
        
        return diff  

    def audit_order_change(self, old_order, user):
        try:
            audit = ChangeHistory(changed_obj=self, changed_by=user, reason=('filter order change: %s' % self.name)[:100])
            audit.save()
            ChangedValue(history=audit, field='order', new_value=str(self.order), old_value=str(old_order)).save()
        except:
            exc = format_exception_info()
            mail_admins('audit failure', 'failed to audit filter order change:\n\n%s\n\n%s' % (self, exc), fail_silently=True)


    def rule_handler_types(self):
        return self.rules.values_list('handler_choice', flat=True).distinct().order_by('handler_choice')
    
    def prepare(self):
        if not self.is_prepared():
            if not self.all_pages and self.page_group:
                self._pages = []
                for p in self.page_group.pages.all():
                    p.prepare()
                    self._pages.append(p)
            else:
                self._pages = False
            
            self._rules = []              
            for r in self.rules.all():
                r.handler.prepare()
                self._rules.append(r)
            self.tracking_method = self.website.tracking_method
            super(Filter, self).prepare()
    
    def check(self, request):
        result = False
        page_match = False
        if self._pages:
            src_page = urllib.unquote_plus(request.GET['l'])
            parsed = urlparse(src_page)
            for p in self._pages:                
                match_path = '%s?%s' % (parsed.path, parsed.query) if p.include_query else parsed.path 
                if p.regex.match(match_path): 
                    page_match = True
                    break
        else:
            page_match = True
        
        if page_match:
            for rule in self._rules:
                result = rule.not_rule ^ rule.handler.check(request)
                if not result: # all must pass                
                    break
        
        return result       


class HandlerBase(models.Model, PrepareMixin):
        
    def full_repr(self):
        return self.__unicode__()

    class Meta:
        abstract = True

class SearchTermHandler(HandlerBase):
    search_terms = models.CharField(max_length=500, verbose_name="Search Terms")
    
    def __unicode__(self):
        return 'search terms [%s]' % (self.search_terms)

    def prepare(self):
        if not self.is_prepared():        
            terms = self.search_terms
            tokens = []
            #1. parse out quoted strings
            m = re.findall(r'(?P<result>(?P<quote>["\']).*?(?P=quote))', terms)
            for t, _ in m:
                terms = terms.replace(t, ' ')
                if len(t.strip()) > 2:
                    tokens.append(re.escape(t.strip()[1:-1]).replace('\ ', '[ ]+'))
            
            #2. split the remainder of the terms string
            for sp in terms.split():
                tokens.append(re.escape(sp).replace('\ ', '[ ]+'))
            
            regex = '|'.join(['(^|[ ])%s([ ]|$)' % token for token in tokens])
            self.regex = re.compile(regex, re.IGNORECASE)
            super(SearchTermHandler, self).prepare()
 
    def check(self, request):
        referrer = request.GET.get('r', None)
        if referrer:
            referrer = urllib.unquote_plus(referrer)
            parsed = urlparse(referrer)
            
            #TODO fix this: deal with different search engines
            terms = parse_qs(parsed.query).get('q', False)
            if terms:
                terms = terms[0]
                return self.regex.search(terms) != None

        return False


class LocationHandler(HandlerBase):
    location_groups = models.ManyToManyField(LocationGroup)
    
    def __unicode__(self):
        s = self.full_repr()
        return s if len(s) <= 90 else s[0:90] + '...'

    def full_repr(self):
        places = []
        for lg in self.location_groups.all():
            for l in lg.locations.all():
                places.append(str(l))
        return 'visitor is from: %s' % '; '.join(places)

        
    def prepare(self):
        if not self.is_prepared():
            self._locations = []
            for lg in self.location_groups.all():
                for locn in lg.locations.all():
                    locn.country_code = locn.country.code
                    self._locations.append(locn)
            super(LocationHandler, self).prepare()

    def check(self, request):
        found = False
        location = GeoIP().city(get_client_ip(request))
        
        if location:
            country_code = location.get('country_code', '--')
            state_code = location.get('region', '--')
            for locn in self._locations:
                if country_code == locn.country_code:
                    if not locn.us_state or state_code == locn.us_state:
                        found = True
                        break
        return found
                        

class ReferralHandler(HandlerBase):
    url = models.URLField(max_length=2048, verify_exists=False, verbose_name="URL", help_text='e.g. http://www.example.com/  and can include * as a wildcard')
    
    def __unicode__(self):
        return 'referred by %s' % (self.url)

    def prepare(self):
        if not self.is_prepared():
            self.regex = re.compile(make_string_safe_for_regex(self.url), re.IGNORECASE)
            super(ReferralHandler, self).prepare()
    
    def check(self, request):
        referrer = request.GET.get('r', None)
        if referrer:
            referrer = urllib.unquote_plus(referrer)
            return self.regex.search(referrer) != None
        else:
            return False


class FrequentVisitorHandler(HandlerBase):
    more_or_less = models.IntegerField(choices=MORE_OR_LESS_CHOICES, default=1)
    visit_count = models.IntegerField(help_text='A visit constitutes any number of pages viewed without a break of 30 minutes or closing the browser')
    time_frame = models.IntegerField(blank=True, null=True)
    
    def __unicode__(self):
        return 'visits %s %s times in %s' % (self.get_more_or_less_display(), self.visit_count, '%s days' % self.time_frame if self.time_frame > 0 else 'unlimited time')

    def check(self, request):
        client_token = request.GET.get('c', None)
        if not client_token:
            return False  # can't track 'em
        
        website_token = request.GET.get('t') # this should already be checked as present
        zkey = get_visits_redis_key(website_token, client_token)
        count = 0
        if hasattr(request, 'redis'):
            now = time.time()
            count = request.redis.execute_command('ZCOUNT', zkey, now - (self.time_frame * 86400) if self.time_frame else 0, now) # zcount(zkey, now - (self.time_frame * 86400) if self.time_frame else 0, now )
        if count == 0: #still here? redis is likely empty...
            from refs.landing.models import ClientVisitStart
            visit_starts = ClientVisitStart.objects.filter(client_identifier=client_token, website_token=website_token)
            
            if hasattr(request, 'redis'):
                pipeline = request.redis.pipeline()
                for start in visit_starts:
                    score = time.mktime(start.visit_date.timetuple())
                    pipeline.zadd(zkey, score, score)
                pipeline.execute()

            if self.time_frame:
                visit_starts = visit_starts.filter(visit_date__gte=datetime.datetime.now() - datetime.timedelta(days=self.time_frame))

            count = visit_starts.count()
        
        return count >= self.visit_count if self.more_or_less == 1 else count < self.visit_count 



DAYS_OF_WEEK = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')

class TimeHandler(HandlerBase):
    date_from = models.DateField(blank=True, null=True, verbose_name="Start Date")
    date_to = models.DateField(blank=True, null=True, verbose_name="End Date")
    
    time_from = models.TimeField(blank=True, null=True, verbose_name="Start Time", help_text='leave blank or set 00:00 to run from the start of the day')
    time_to = models.TimeField(blank=True, null=True, verbose_name="End Time", help_text='leave blank to run through to the end of the day')
    
    monday = models.BooleanField(default=True, verbose_name='mon')
    tuesday = models.BooleanField(default=True, verbose_name='tue')
    wednesday = models.BooleanField(default=True, verbose_name='wed')
    thursday = models.BooleanField(default=True, verbose_name='thu')
    friday = models.BooleanField(default=True, verbose_name='fri')
    saturday = models.BooleanField(default=True, verbose_name='sat')
    sunday = models.BooleanField(default=True, verbose_name='sun')
    
    timezone = models.CharField(max_length=100, choices=TZ_CHOICES)
    
    def __unicode__(self):
        days = ''
        if self.monday and self.tuesday and self.wednesday and self.thursday and self.friday:
            if not self.saturday and not self.sunday:
                days = 'weekdays'
            elif self.saturday and self.sunday:
                days = 'any day'
            else:
                days = 'Mon-Sat' if self.saturday else 'Sun-Fri'
        elif self.saturday and self.sunday and not (self.monday or self.tuesday or self.wednesday or self.thursday or self.friday):
            days = 'weekends'
        else:
            setodays = []
            for fld in DAYS_OF_WEEK:
                if getattr(self, fld):
                    setodays.append(fld[0:3].capitalize())
            days = ', '.join(setodays)
                
        return u'%s - %s, %s - %s on %s' % \
            ('%s (inc.)' % self.date_from.strftime('%Y-%m-%d') if self.date_from else 'any date', 
             '%s (inc.)' % self.date_to.strftime('%Y-%m-%d') if self.date_to else 'any date', 
             'start of day' if not self.time_from else '%s (inc.)' % self.time_from, 
             'end of day' if not self.time_to else '%s (exc.)' % self.time_to, 
             days)

    def compare_dates(self, tz_now, tz):
        naive_now = datetime.date(tz_now.year, tz_now.month, tz_now.day)
        
        return  (not self.date_from or naive_now >= self.date_from) and \
                (not self.date_to or naive_now <= self.date_to )

    def check_day_of_week(self, tz_now):
        weekday = tz_now.weekday()
        
        return getattr(self, DAYS_OF_WEEK[weekday])
    
    
    def compare_times(self, tz_now):
        naive_now = datetime.time(tz_now.hour, tz_now.minute)
        
        return (not self.time_from or naive_now >= self.time_from) and \
                (not self.time_to or naive_now < self.time_to)
        
    def check(self, request):        
        tz = timezone(self.timezone)
        tz_now = datetime.datetime.now(utc).astimezone(tz)
        
        return  self.compare_dates(tz_now, tz) and \
                self.check_day_of_week(tz_now) and \
                self.compare_times(tz_now)
     

class QueryStringHandler(HandlerBase):
    query_string = models.CharField(max_length=2048, help_text='Can include * as a wildcard', verbose_name="Campaign Code")
    
    def __unicode__(self):
        return 'campaign code contains "%s"' % self.query_string

    def prepare(self):
        if not self.is_prepared():
            self.regex = re.compile(make_string_safe_for_regex(self.query_string), re.IGNORECASE)
            super(QueryStringHandler, self).prepare()
            
    def check(self, request):
        location =  urllib.unquote_plus(request.GET.get('l', ''))
        url = urlparse(location)
        if url.query:
            return self.regex.search(url.query) != None
        else:
            return False

            
class AlertSchedule(models.Model):
    website = models.ForeignKey(Website, related_name="alertschedules")
    name = models.CharField(max_length='200')
    
    def __unicode__(self):
        return self.name
        

##### Forms
class FilterListForm(forms.Form):
    filter_order = forms.CharField(max_length=8000, required=False, widget=forms.HiddenInput)
    filter_on_off = forms.ModelMultipleChoiceField(required=False, queryset=Filter.objects.get_empty_query_set())

    def __init__(self, filters, **kwargs):
        super(FilterListForm, self).__init__(**kwargs)

        self.fields['filter_on_off'].queryset=filters    

class WebsiteForm(forms.ModelForm):
    
    def __init__(self, **kwargs):
        super(WebsiteForm, self).__init__(**kwargs)
        self.fields['include_subdomains'] = forms.BooleanField(required=False,
                                                initial=(not (self.instance.exact_match if self.instance else True)),
                                                label="Include Subdomains")
        self.fields['ga_event_tracking'] = forms.BooleanField(required=False,
                                                initial=(not (self.instance.tracking_method == 'non' if self.instance else False)),
                                                label="Track in Google Analytics")
        
    def clean(self):
        self.cleaned_data['exact_match'] = not self.cleaned_data.get('include_subdomains', not self.instance.exact_match)
        self.cleaned_data['tracking_method'] = 'evt' if self.cleaned_data.get('ga_event_tracking', False) else 'non'
        
        return self.cleaned_data
    
    class Meta:
        model = Website
        fields = ('name', 'exact_match', 'tracking_method')

class WebsiteUserForm(forms.ModelForm):
    
    def display_user(self):
        return self.instance.user.email if self.instance else None
    
    def display_website(self):
        return self.instance.website if self.instance else None
    
    class Meta:
        model = WebsiteUser
        fields = ('level',)

class UserInviteForm(forms.ModelForm):
    
    class Meta:
        model = UserInvite
        fields = ('email', 'level',)
        
        
class FilterForm(forms.ModelForm):
    test_url = forms.CharField(max_length=2048, required=False)
    
    def __init__(self, rules_qs, **kwargs):
        super(FilterForm, self).__init__(**kwargs)
        #self.fields.pop('rules')
        #self.fields.pop('page_groups')
        #self.fields.insert(3,'rules',forms.ModelMultipleChoiceField(queryset=rules_qs))
        #self.fields.insert(4,'page_groups',forms.ModelMultipleChoiceField(queryset=pagegroups_qs, required=False))

        self.fields['rules'].queryset=rules_qs
        
    class Meta:
        model = Filter
        exclude = ('website', 'order', 'deleted' )
        widgets = {'all_pages': forms.RadioSelect,
                   'html': Textarea(attrs={'cols': 60, 'rows': 5}),
                   'code': Textarea(attrs={'cols': 60, 'rows': 8}),}

class RuleForm(forms.ModelForm):
    def __init__(self, existing_rule_types, **kwargs):
        super(RuleForm, self).__init__(**kwargs)
        
        limited_choices = []
        for t in HANDLER_CHOICES:
            if t[0] == self.instance.handler_choice or t[0] not in existing_rule_types or t[0] not in ONE_RULE_ONLY:
                limited_choices.append(t)
        self.fields['handler_choice'] = forms.ChoiceField(choices=tuple(limited_choices),
                                                          initial=self.instance.handler_choice,
                                                          label="Rule Type")
    
    def clean_handler_choice(self):
        choice= self.cleaned_data['handler_choice']
        if choice:
            return int(choice)
        else:
            raise forms.ValidationError('Choose a Rule Type')
 
    class Meta:
        model = Rule
        fields = ('name', 'handler_choice', 'not_rule')

class QuerysetOverrideForm(forms.ModelForm):
    
    def override_querysets(self, qs):
        for k, v in qs.items():
            if k in self.fields:
                self.fields[k].queryset=v

class TimeHandlerForm(forms.ModelForm):
    
    def clean(self):
        if self.cleaned_data.get('date_to', False) and self.cleaned_data['date_to'] <= (datetime.date.today() - datetime.timedelta(days=1)):
            self._errors['date_to'] = ErrorList([u'End Date is in the past, the rule will never match'])
            
        if self.cleaned_data.get('date_from', False) and self.cleaned_data.get('date_to', False) \
                and self.cleaned_data['date_from'] > self.cleaned_data['date_to']:
            self._errors['date_to'] = ErrorList([u'End Date must be the same as or later than Start Date'])
                
        if  self.cleaned_data.get('time_from', False) and self.cleaned_data.get('time_to', False) \
                and self.cleaned_data['time_from'] >= self.cleaned_data['time_to']:
            self._errors['time_to'] = ErrorList([u'End Time must be later than Start Time'])
        
        one_day = False
        for fld in DAYS_OF_WEEK:
            if fld in self.cleaned_data and self.cleaned_data[fld]:
                one_day = True
                break
        
        if not one_day:
            self._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([u'You must choose at least one day else the rule will never match'])
        
        return self.cleaned_data
        
        
    class Meta:
        model = TimeHandler

class SearchTermHandlerForm(forms.ModelForm):

    class Meta:
        model = SearchTermHandler



_location_choices = []
try:
    for c in Country.objects.all():
        _location_choices.append(tuple([c.id, c.name]))
        if c.code == "US":
            for state_code, state in us_states.STATE_CHOICES:
                _location_choices.append(tuple(['%s:%s' % (c.id, state_code), '%s, US' % state]))
except DatabaseError:
    exc = format_exception_info()
    logging.error('Error initialising LOCATION_CHOICES')
    logging.error(exc)

LOCATION_CHOICES = tuple(_location_choices)
OPTIONAL_STATE_CHOICES = (('', 'Any State'),) + us_states.STATE_CHOICES

class LocationHandlerForm(QuerysetOverrideForm):
    locations = forms.MultipleChoiceField(choices=LOCATION_CHOICES)
    country = forms.ModelChoiceField(queryset=Country.objects.all(), required=False)
    state = forms.ChoiceField(choices=OPTIONAL_STATE_CHOICES, required=False)
    
    def coerce_data(self):
        if self.instance and self.instance.id:
            locations = []
            for lg in self.instance.location_groups.all():
                for l in lg.locations.all():
                    locations.append('%s%s' % (l.country.id, '' if not l.us_state else ':%s' % l.us_state ))
            self.initial['locations'] = locations
        
    def save(self, commit=True, *args, **kwargs):
        if not commit:
            raise RuntimeError('Must not save LocationHandler uncommitted')
        #basic save
        lh = super(LocationHandlerForm, self).save(commit=True)
        
        try:
            lg = lh.location_groups.get(name=lh.id)
        except LocationGroup.DoesNotExist:
            lg = lh.location_groups.create(name=lh.id)
        else:
            lg.locations.clear()
            
        places = self.cleaned_data.get('locations')
        for place in places:
            split = place.split(':')
            country = Country.objects.get(id=split[0])
            if len(split) > 1:
                lg.locations.create(country=country, us_state=split[1])
            else:
                lg.locations.create(country=country)
        
        return lh
    
    class Meta:
        model = LocationHandler
        exclude = ('location_groups',)

class FrequentVisitorHandlerForm(forms.ModelForm):
    
    def clean_time_frame(self):
        tf = self.cleaned_data.get('time_frame', None) 
        if tf != None and tf <= 0:
            raise forms.ValidationError('Time Frame must be greater than 0 or leave blank for unlimited time')
        return tf
    
    def clean_visit_count(self):
        vc = self.cleaned_data.get('visit_count', None)
        if vc <= 0:
            raise forms.ValidationError('Visit Count must be greater than 0')
        return vc
    
    def clean(self):
        if self.cleaned_data.get('more_or_less', None) == 2 and self.cleaned_data.get('visit_count', 2) < 2:
            self._errors['visit_count'] = ErrorList([u'"Fewer than" 1 visit is not possible'])
        
        return self.cleaned_data

        
    class Meta:
        model = FrequentVisitorHandler

class ReferralHandlerForm(forms.ModelForm):
    
    class Meta:
        model = ReferralHandler

class QueryStringHandlerForm(forms.ModelForm):
    
    class Meta:
        model = QueryStringHandler

class PageGroupForm(forms.ModelForm):
    
    class Meta:
        model = PageGroup
        exclude = ('website',)

class PageForm(forms.ModelForm):

    def clean_url(self):
        url = self.cleaned_data.get('url', None)
        if url and len(url) > 0 and url[0] not in '*/':
            return '/' + url
        return url
            
    class Meta:
        model = Page
        
PageInlineFormSet = inlineformset_factory(PageGroup, Page, form=PageForm, extra=1)

HANDLER_FORMS = {
    10: ReferralHandlerForm,
    20: QueryStringHandlerForm,
    30: SearchTermHandlerForm,
    50: TimeHandlerForm,
    60: LocationHandlerForm,
    70: FrequentVisitorHandlerForm,  
}
