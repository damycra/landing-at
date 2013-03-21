from refs.utils import random_token, set_message,\
    get_filter_hits_by_day_redis_key, get_filter_hits_redis_key
from django.contrib.auth.models import User
import string
import uuid
from django.contrib.auth import authenticate, login
from refs.accounts.models import Account
from refs.rules.models import Website, WebsiteUser, RULE_EDIT, Filter
from django.shortcuts import redirect
from django.core.urlresolvers import reverse
import datetime
from refs.landing.records import get_redis
import random


class SandboxMiddleware:
    
    def process_request(self, request):
        path = request.path_info.lower()
        
        if not path.startswith("/admin/"):
            request.is_sandbox = True
        
        if request.method == 'POST' and path.startswith("/accounts/"):
            set_message(request, 'sandbox_deny_post', level='attention')
            return redirect(request.path_info)
        

class AccountSetupMiddleware:
    
    def process_request(self, request):
        if request.user.is_anonymous() and getattr(request, 'is_sandbox', False):
            random_string = random_token(string.ascii_letters[:26])
            email = 'e%s@example.com' % random_string
            password = str(uuid.uuid4())
            User.objects.create_user('demo_%s' % random_string, 
                                                 email, 
                                                 password)
            authed_user = authenticate(username=email, password=password)
            login(request, authed_user)
            
            authed_user.first_name = 'Demo'
            authed_user.last_name = 'User'
            authed_user.save()
            
            accounts = Account.objects.all()
            if accounts:
                account = accounts[0]
            else:
                su = User.objects.get(pk=1)
                account = Account(owner=su)
                account.save()
            
            website = Website(account=account, name='www.example.com', exact_match=True, verified_date=datetime.datetime.now())
            website.save()
            WebsiteUser(website=website, user=authed_user, level=RULE_EDIT).save()

            today = datetime.datetime.today()
            redis = get_redis(backup=True)
            for filter in Filter.objects.filter(website__id=1):
                exemplar_fid = filter.id                    
                filter.id = None
                filter.website = website
                filter.save()
                
                #now semi-deep copy: copy rules to set correct website but not handlers: they will be saved anew on edits
                exemplar_filter = Filter.objects.get(pk=exemplar_fid)
                for rule in exemplar_filter.rules.all():
                    rule.id = None
                    rule.website = website
                    rule.save()
                    filter.rules.add(rule)
                    
                # make up some stats
                for i in range(0,14):
                    redis.set( get_filter_hits_by_day_redis_key(website.token, filter.id, today - datetime.timedelta(days=i)), random.randint(50,250))
                redis.set( get_filter_hits_redis_key(website.token, filter.id), 2) #needed to avoid DB lookup
                
            return redirect(reverse('filters', args=[website.id]))
            
