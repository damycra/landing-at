from django.db import models
from django import forms
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from registration.signals import user_registered

from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import login, authenticate
from django.core.mail import mail_managers
from django.forms.util import ErrorList
from refs.accounts.backends import RegistrationBackend
import datetime
from django.contrib.localflavor.us import us_states
#from django.contrib.gis.utils.geoip import GeoIP
from refs.utils import get_client_ip, format_exception_info
from refs import settings
from django.template.loader import render_to_string
from django.core.mail.message import EmailMessage
import logging
import sys
from recurly import Recurly, RecurlyException


# Create your models here.    
#class UserSubscription(models.Model):
#    user = models.ForeignKey(User, related_name='subscriptions')
#    code = models.ForeignKey(SubscriptionCode)
#    shipping_address = models.ForeignKey('Address', blank=True, null=True)
#    is_active = models.BooleanField(default=True)
#    created_date = models.DateTimeField(auto_now_add=True)
#    updated_date = models.DateTimeField(auto_now=True)
#    updated_reason = models.CharField(max_length=30, default='New subscription')
#
#    def __unicode__(self):
#        return "%s subscription for %s (%s)" % ('Active' if self.is_active else 'Inactive', self.user.email, self.code)
#        
#    class Meta:
#        ordering = ['-is_active', '-created_date']

def trial_period_ends():
    return datetime.datetime.now() + datetime.timedelta(days=30)

class Account(models.Model):
    owner = models.ForeignKey(User, related_name='accounts')

    trial_period_ends = models.DateTimeField(default=trial_period_ends, null=True)
    
    def __unicode__(self):
        return 'Account owned by %s' % (self.owner.email)

class Currency(models.Model):
    name = models.CharField(max_length=20)
    code = models.CharField(max_length=3, unique=True)
    html_symbol = models.CharField(max_length=10)
    per_dollar = models.FloatField()

    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name_plural = "currencies"


class Country(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    priority = models.SmallIntegerField(default=0, help_text="larger numbers order higher")
    default_currency = models.ForeignKey(Currency, help_text='Customers from this country will purchase in this currency', 
                                         verbose_name='purchase currency')
    is_eu = models.BooleanField(default=False,verbose_name='EU member?')

    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "countries"
        ordering = ['-priority', 'name']

    
class UserProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    
    country = models.ForeignKey(Country, null=True)
    state = models.CharField(max_length=2, blank=True, choices=us_states.STATE_CHOICES)
    
    show_advanced_options = models.BooleanField(blank=True, default=False)
    
    email_optin = models.BooleanField(blank=True, default=True)
    
    telephone_number = models.CharField(max_length=20, blank=True)
    last_website_id = models.IntegerField(default=0)
        
    def __unicode__(self):
        return self.user.email

#    def get_billing_address(self, last_chance=False):
#        ''' find the most recent billing address from an invoice, or fall back
#            to find a shipping address if no invoices exist and if last_chance=False 
#        '''
#        from xbcms.shop.models import Invoice
#        invoices = Invoice.objects.filter(user=self.user).order_by('-created_date')
#        
#        for i in invoices:
#            if i.billing_address:
#                return i.billing_address
#        
#        return None if last_chance else self.get_shipping_address(last_chance=True) 
#        
#    def get_shipping_address(self, last_chance=False):
#        ''' find the most recent shipping address from a subscription, or fall back to find 
#            a billing address if last_chance=False
#        '''
#        subs = UserSubscription.objects.filter(user=self.user).order_by('-created_date')
#        
#        for s in subs:
#            if s.shipping_address:
#                return s.shipping_address
#        
#        return None if last_chance else self.get_billing_address(last_chance=True)
    
#    @models.permalink
#    def get_absolute_url(self):
#        return ('public_user_profile', [self.id]) 
           

class Address(models.Model):
    user = models.ForeignKey(User)
    name = models.CharField(max_length=100)
    address_1 = models.CharField(max_length=80)
    address_2 = models.CharField(max_length=80, blank=True)
    address_3 = models.CharField(max_length=80, blank=True)
    town_city = models.CharField(max_length=80, verbose_name='Town/City')
    postal_code = models.CharField(max_length=15, verbose_name='Zip/Postal code')
    state = models.CharField(max_length=2, blank=True, choices=us_states.STATE_CHOICES)
    country = models.ForeignKey(Country)
    telephone_number = models.CharField(max_length=20, blank=True)
    created_date = models.DateTimeField(auto_now_add=True, editable=False)
    
    def __unicode__(self):
        return "%s (%s)" % (self.address_1, self.user.email)
    
    def full_address(self):
        address = [self.name, self.address_1]
        if self.address_2: address.append(self.address_2)
        if self.address_3: address.append(self.address_3)
        address.append(self.town_city)
        address.append(self.postal_code)
        if self.country.code == 'US' and self.state: address.append(self.get_state_display())
        address.append(self.country.name)
        
        return "\n".join(address)
    
    class Meta:
        verbose_name_plural = 'Addresses'        

#SIGNALS        
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        up = UserProfile(user=instance)
        up.save()

def on_user_registered(sender, user, request, **kwargs):
    from refs.accounts.forms import UserProfileRegistrationForm

    up = user.get_profile()
    form = UserProfileRegistrationForm(request.POST) #this _should_ already be valid
    if form.is_valid():
        name = form.cleaned_data.get('name', '')
        name_split = name.split()
        if len(name_split) > 0:
            user.first_name = name_split[0]
            if len(name_split) > 1:
                user.last_name = ' '.join(name_split[1:])
        user.save()
        
        try:
            location = None # GeoIP().city(get_client_ip(request))
            if location:
                country_code = location.get('country_code')
                state_code = location.get('region', 'zzzz')
                
                try:
                    ctry = Country.objects.get(code=country_code)
                except Country.DoesNotExist:
                    pass
                else:
                    up.country = ctry
                    if country_code == 'US':
                        up.state = us_states.STATES_NORMALIZED.get(state_code.lower(), '')
        except:
            logging.error('Error in geolocation during registration', exc_info=sys.exc_info())
            
        up.email_optin = form.cleaned_data['email_optin']
        
        up.save()    
        
        if user.authorised_websites.count() == 0:
            acct = Account(owner=user)
            acct.save()
            recurly_data = {
                'account_code': user.email,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
            recurly = Recurly(**settings.RECURLY)
            try:
                recurly_account = recurly.accounts.create(data=recurly_data)
            except RecurlyException:
                exc = format_exception_info()
                logging.error('Recurly error for %s: %s;%s;' % (user.email, exc[0], exc[1]), exc_info=sys.exc_info() )
                mail_managers('Recurly error', 'Exception creating account for %s; please investigate/fix\n\n%s\n%s' % (user.email, exc[0], exc[1]), fail_silently=False)
                recurly_account = {'account_code': user.email, 'hosted_login_token': 'pending'}
            
            default_price_plan_qs = PricePlan.objects.filter(active=True, default=True)
            user_plan = UserPlan(price_plan=default_price_plan_qs[0], account=acct, 
                                 recurly_account_code=recurly_account['account_code'],
                                 recurly_login_token=recurly_account['hosted_login_token'],)
            user_plan.save()
        
        if settings.SEND_REGISTRATION_EMAIL:
            email_body = render_to_string("registration/registration_email.txt", { 'user': user,})
            email_subject = render_to_string("registration/registration_email_subject.txt") 
            email = EmailMessage(email_subject.splitlines()[0], email_body, settings.REG_EMAIL,
                                 [user.email], [settings.REG_EMAIL],
                                 headers={'Reply-To': settings.REG_EMAIL})
            email.send(fail_silently=True)
                    
    else:
        raise RuntimeError(form.errors)
        
            
post_save.connect(create_user_profile, sender=User)
user_registered.connect(on_user_registered, sender=RegistrationBackend)
    


class PricePlan(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, help_text='must match url code in recurly')
    description = models.TextField(blank=True)
    level = models.PositiveIntegerField(help_text='determines whether transition is an upgrade/downgrade. e.g. level=1 to level=3 would be an upgrade')
    
    fhits = models.PositiveIntegerField(help_text='filter hits included in fixed charge')
    fixed_charge = models.DecimalField(max_digits=7, decimal_places=2)
    
    extra_fhits = models.PositiveIntegerField(help_text='size of extra block of filter hits')
    bundle_charge = models.DecimalField(max_digits=7, decimal_places=2)
    
    billing_period = models.PositiveIntegerField(default=1, help_text='months between bills')
    active = models.BooleanField(default=True, help_text='available for new customers?')

    default = models.BooleanField(help_text='default plan for totally new users. There should only be one of these active at a time')

    def __unicode__(self):
        return '%s (%s)' % (self.name, self.active and 'active' or 'inactive')
    

    
class UserPlan(models.Model):
    price_plan = models.ForeignKey(PricePlan)
    account = models.ForeignKey(Account, related_name='user_plans')
    
    recurly_account_code = models.CharField(max_length=300)
    recurly_login_token = models.CharField(max_length=40)
    card_set_up = models.BooleanField(default=False)

    max_monthly_overage = models.DecimalField(max_digits=7, decimal_places=2, help_text='set a max overage budget per calendar month', default=0)
    notify_extras = models.BooleanField(default=False, help_text='send an email when a new charge is raised')

    overage_this_month = models.DecimalField(max_digits=7, decimal_places=2, help_text='', default=0)

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    end_date = models.DateTimeField(null=True, blank=True)    


#ModelForms
class UserProfileForm(forms.ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'
    
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
        
    def clean(self, *args, **kwargs):
        super(UserProfileForm, self).clean(*args, **kwargs)
                
        if 'country' in self.cleaned_data and self.cleaned_data['country'].code == 'US' and not self.cleaned_data['state']:
            self._errors['state'] = ErrorList([u'Choose a State'])
                
        return self.cleaned_data

    class Meta:
        model = UserProfile
        exclude = ('user', 'last_website_id')


class AddressForm(forms.ModelForm):

    def clean(self, *args, **kwargs):
        super(AddressForm, self).clean(*args, **kwargs)
                
        if 'country' in self.cleaned_data and self.cleaned_data['country'].code == 'US' and not self.cleaned_data['state']:
            self._errors['state'] = ErrorList([u'Choose a State'])
    
        return self.cleaned_data
    
    class Meta:
        model = Address
        exclude = ('user',)


