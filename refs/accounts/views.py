# Create your views here.
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.generic.simple import direct_to_template, redirect_to
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from refs.accounts.models import UserProfileForm, PricePlan, UserPlan
from refs.accounts.forms import InvitedUserProfileRegistrationForm
from refs.rules.models import UserInvite
from refs.rules.context_processors import populate_website_and_user_permissions
from registration.views import register
from refs.utils import set_message
from recurly import Recurly, RecurlyException, RecurlyConnectionException, RecurlyValidationException
from refs import settings
import datetime
import logging

@csrf_protect
@login_required
def edit_profile(request):
    up = request.user.get_profile()
    if request.method == 'POST': # If the form has been submitted...
        form = UserProfileForm(request.POST, instance=request.user.get_profile()) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save()
            form.save()
            set_message(request, 'saved_profile', context={'user':request.user})
            website_context = populate_website_and_user_permissions(request)
            website = website_context.get('website', None)
            if not website:
                for wuser in request.user.authorised_websites.all():
                    website = wuser.website
                    break
            if not website:
                set_message(request, 'no_permissions', level='attention', context={'user': request.user})
                return HttpResponseRedirect(reverse("create_account"))
            else:
                return HttpResponseRedirect(reverse('administer_site', args=[website.id])) # Redirect after POST    
    else:
        form = UserProfileForm(instance=up, 
                               initial={'first_name' : request.user.first_name, 
                                        'last_name' : request.user.last_name,
                                       })
    return direct_to_template(request, template="registration/edit_profile.html", extra_context={'upform': form })    

    
@login_required
def view_profile(request):
    if request.user.authorised_websites.count() > 0:
        return redirect_to(request, reverse('filters', args=[request.user.authorised_websites.all()[0].website.id]))
    else:
        return redirect_to(request, reverse('add_website'))

@csrf_protect
@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            set_message(request, 'password_changed', context={'user' : request.user})
            return HttpResponseRedirect(reverse('user_profile'))
    else:
        form = PasswordChangeForm(user=request.user)
        
    return direct_to_template(request, template='registration/password_change_form.html', 
                              extra_context={'form': form,})


def register_with_token(request, token, backend):
    extra_context={'token': token}
    if request.method == 'POST': # delegate to the registration app
        return register(request, backend, form_class=InvitedUserProfileRegistrationForm, extra_context=extra_context, success_url='root')
    else:
        try:
            invite = UserInvite.objects.get(token=token)
        except UserInvite.DoesNotExist:
            form = InvitedUserProfileRegistrationForm(initial={'token': token})
        else:
            form = InvitedUserProfileRegistrationForm(initial={'token': token, 'email':invite.email})
            extra_context['email'] = invite.email
    
    extra_context['form'] = form
    return direct_to_template(request, template='registration/registration_form.html', extra_context=extra_context)
            
@login_required
def create_account(request):
    raise NotImplementedError()                


def get_user_plan(request):
    user_plan = request.user.accounts.all()[0].user_plans.filter(end_date__isnull=True)[0]
    
    return user_plan

@login_required
def show_invoices(request):
    user_plan = get_user_plan(request)
    recurly = Recurly(**settings.RECURLY)
    pending = recurly.accounts.charges(account_code=user_plan.recurly_account_code, show='pending') or {}
    invoices = recurly.accounts.invoices(account_code=user_plan.recurly_account_code) or {}
    
    charge_summaries = []
    for c in pending.get('charge', []):
        date = datetime.datetime.strptime(c['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        charge_summaries.append({'description': c['description'], 'amount': float(c['amount_in_cents'])/100.0, 'date': date})
    
    invoice_summaries = []
    for i in invoices.get('invoice', []):
        date = datetime.datetime.strptime(i['date'], '%Y-%m-%dT%H:%M:%SZ')
        invoice_summaries.append({'ex_tax': float(i['subtotal_in_cents'])/100.0, 'inc_tax': float(i['total_in_cents'])/100.0, 'number': i['invoice_number'], 'date': date  })
    
    return direct_to_template(request, template='registration/invoices.html', 
                              extra_context={'user_plan': user_plan,
                                             'pending_charges': charge_summaries,
                                             'invoices': invoice_summaries,
                                             'account': user_plan.account })


@login_required
def subscribed(request):
    user_plan = get_user_plan(request)
    recurly = Recurly(**settings.RECURLY)
    subscription = recurly.accounts.subscription(account_code=user_plan.recurly_account_code)
    if subscription['state'] != 'active':
        raise RuntimeError('subscription is not active')
    price_plan = PricePlan.objects.get(slug=subscription['plan']['plan_code'])
    new_user_plan = UserPlan(price_plan=price_plan, account=user_plan.account, 
                         recurly_account_code=subscription['account_code'],
                         recurly_login_token=user_plan.recurly_login_token,
                         card_set_up=True)
    user_plan.end_date = datetime.datetime.now()
    user_plan.save()
    new_user_plan.save()
    
    set_message(request, 'subscribed', context={'new_user_plan': new_user_plan})
    return redirect_to(request, reverse('administer_site',args=[request.user.get_profile().last_website_id]))


@login_required
def change_plan(request):
    if request.method == 'POST':
        user_plan = get_user_plan(request)
        new_plan = request.POST.get('plan')
        new_price_plan = PricePlan.objects.filter(active=True, slug=new_plan)
        if new_plan != user_plan.price_plan.slug and new_price_plan:
            recurly = Recurly(**settings.RECURLY)
            
            update_data = {
              'timeframe': 'renewal',
              'plan_code': new_plan,
            }
            update_result = recurly.accounts.subscription.update(account_code=user_plan.recurly_account_code, data=update_data)
            logging.debug(update_result)
            
            new_user_plan = UserPlan(price_plan=new_price_plan[0], account=user_plan.account, 
                                 recurly_account_code=update_result['account_code'],
                                 recurly_login_token=user_plan.recurly_login_token,
                                 card_set_up=user_plan.card_set_up)
            user_plan.end_date = datetime.datetime.now()
            user_plan.save()
            new_user_plan.save()
            
            set_message(request, 'plan_changed', context={'old_user_plan': user_plan, 'new_user_plan': new_user_plan})
            return redirect_to(request, reverse('administer_site',args=[request.user.get_profile().last_website_id]))
        else:
            set_message(request, 'plan_not_changed', level='attention', context={'user_plan': user_plan})
            return redirect_to(request, reverse('choose_plan'))  
    else:
        return HttpResponseBadRequest()

@login_required
def choose_plan(request):
    user_plan = get_user_plan(request)
    
    upgrades = PricePlan.objects.filter(level__gt=user_plan.price_plan.level, active=True)
    downgrades = PricePlan.objects.filter(level__lt=user_plan.price_plan.level, active=True)
    crossgrades = PricePlan.objects.filter(level=user_plan.price_plan.level, active=True) if not user_plan.price_plan.active else []
    all_plans = PricePlan.objects.filter(active=True)
    
    return direct_to_template(request, template='registration/plan_choice.html', 
                              extra_context={'user_plan': user_plan,
                                             'user_plan_level': user_plan.price_plan.level,
                                             'upgrades': upgrades,
                                             'downgrades': downgrades,
                                             'crossgrades': crossgrades,
                                             'all_plans': all_plans,
                                             'recurly_url': settings.RECURLY_HOSTED_URL,})

@csrf_exempt    
def handle_notification(request):
    if request.method == 'POST':
        xml =  request.raw_post_data
        recurly = Recurly(**settings.RECURLY)
        note_type = recurly.parse_notification(xml)
        note_data = recurly.response
        
        
        print note_type, note_data
    