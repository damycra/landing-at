# Create your views here.
from django.shortcuts import get_object_or_404, redirect
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.views.generic.list_detail import object_list
from django.views.generic.simple import direct_to_template
from refs.rules.models import WebsiteForm, RULE_EDIT, FilterForm, Website,\
    Filter, ADMIN, READ_ONLY, PageGroup, PageInlineFormSet,\
    RuleForm, HANDLER_FORMS, Rule, WebsiteUser,\
    UserInvite, UserInviteForm, ALL_PAGES,\
    HANDLER_CHOICES_DICT, FilterListForm
from django.template.loader import render_to_string
from django.utils import simplejson
from django.db.models import Max, Q
from django.core.mail import send_mail
from django.contrib.auth.models import User
from urllib2 import URLError, HTTPError
from BeautifulSoup import BeautifulSoup, Comment, Tag
from refs import settings
from urlparse import urlparse
import datetime
import logging
import urllib2
import re
from refs.utils import format_exception_info, set_message
from refs.landing.records import get_filter_hits

@login_required
def index(request):
    last_website_id = request.user.get_profile().last_website_id
    authed_sites = request.user.authorised_websites.all()
    if last_website_id > 0 and authed_sites.filter(website__id=last_website_id):
        website = authed_sites.filter(website__id=last_website_id)[0].website
    elif authed_sites.count() > 0:
        website = request.user.authorised_websites.all()[0].website
    else:
        website = None
        
    if website:
        if website.verified_date:
            return redirect('filters', (website.id))
        else:
            return redirect('view_website', (website.id))
    
    # no website
    if request.user.accounts.count() > 0:
        return redirect('add_website')
    else:
        return redirect('create_account')

@login_required
def view_websites(request):
    
    return object_list(request, queryset=request.user.authorised_websites.all(), 
                       template_object_name='websiteuser')

def get_website(request, id, min_level=RULE_EDIT):
    website = get_object_or_404(Website, id=id)
    if not website.authorised_users.filter(user=request.user, level__gte=min_level).exists():
        raise Http404
    
    request._website = website
    return website


@login_required
def view_website(request, id): 
    get_website(request, id, min_level=READ_ONLY)

    new_website = request.session.get('new_website_%s' % id, False)
    if new_website:
        del request.session['new_website_%s' % id]

    return direct_to_template(request, template='rules/websites/website_detail.html',
                              extra_context = {'new_website': new_website,
                                               'show_setup_tab': True}) 


@login_required
def add_edit_website(request, id=None):
    if id:
        website = get_website(request, id)
    else:
        try:
            account = request.user.accounts.all()[0]
        except KeyError:
            raise Http404()
        else:
            website = Website(account=account)
            request._website = website
    
    if request.method == 'POST':
        audit_obj = website.audit_fields() if id else None
        form = WebsiteForm(data=request.POST, instance=website)
        
        if form.is_valid():
            saved_website = form.save()
            
            if not id:
                website.authorised_users.create(user=request.user, website=website, level=ADMIN)
                website.audit_simple_change('++ CREATED ++', request.user)
            else:
                website.audit_update(audit_obj, request.user)
            
            set_message(request, 'saved_website', context={ 'website' : website })
            if not id:
                request.session['new_website_%s' % saved_website.id] = True 
                return redirect('view_website', (website.id))
            else: 
                set_cache_warning_message(request, website)
                return redirect('administer_site', (website.id))  
    else:
        form = WebsiteForm(instance=website)
    
    return direct_to_template(request, template='rules/websites/add_edit_website.html', 
                              extra_context = {'form':form,
                                               'new_website': False if id else True,})


@login_required
def filters(request, website_id):
    if request.method == 'POST':
        website = get_website(request, website_id)
        form = FilterListForm(website.filters.filter(deleted=False), data=request.POST)
        
        if form.is_valid():
            filter_order = form.cleaned_data.get('filter_order', None)
            filter_on_off = form.cleaned_data.get('filter_on_off', [])
            order_change = False
            if filter_order:
                website_filters = website.filters.filter(deleted=False)
                for spec in filter_order.split():
                    id, ord = spec.split(':')
                    filter = website_filters.get(id=id)
                    if int(ord) != filter.order:
                        order_change = True
                        old_order = filter.order
                        filter.order = ord
                        filter.save()
                        filter.audit_order_change(old_order, request.user)
                if order_change:
                    set_cache_warning_message(request, website)
                    set_message(request, 'new_order', context={ 'website' : website })
            filter_change = False
            for filter in website.filters.filter(deleted=False):
                if filter.active and filter not in filter_on_off:
                    filter.active = False
                    filter.save()
                    filter.audit_simple_change('DE-ACTIVATED', request.user)
                    set_message(request, 'de-activated_filter', context={ 'filter' : filter })
                    filter_change = True
                elif not filter.active and filter in filter_on_off:
                    filter.active = True
                    filter.save()
                    filter.audit_simple_change('ACTIVATED', request.user)
                    set_message(request, 'de-activated_filter', context={ 'filter' : filter })
                    filter_change = True
            
            if filter_change and not order_change:
                set_cache_warning_message(request, website)
                    
            return redirect('filters', (website.id))
    else:
        website = get_website(request, website_id, min_level=READ_ONLY)
        form = FilterListForm(website.filters.filter(deleted=False))
    
    filter_hits = get_filter_hits(website.token, days=14)
        
    return direct_to_template(request, template='rules/filters/filters.html', 
                              extra_context = {'form':form, 'filter_hits': filter_hits})


@login_required
def add_edit_filter(request, website_id, filter_id=None):
    website = get_website(request, website_id)
    filter = get_object_or_404(website.filters.filter(deleted=False), id=filter_id) if filter_id else Filter(website=website)
    pagegroup = filter.page_group if not filter.all_pages else PageGroup(website=website)
    rules = website.rules.all() 
    if request.method == 'POST':
        audit_obj = filter.audit_fields() if filter_id else None
        form = FilterForm(rules, data=request.POST, instance=filter)
        page_formset = PageInlineFormSet(request.POST, instance=pagegroup)
        if form.is_valid():
            if form.cleaned_data['all_pages'] or page_formset.is_valid():
                filter = form.save()
                if filter.all_pages:
                    filter.page_group = None
                else:
                    pagegroup.save()
                    page_formset.save()
                    filter.page_group = pagegroup
                    
                if not filter_id: #specify a unique order
                    max_order = website.filters.aggregate(Max('order'))
                    filter.order = max_order.get('order__max', 0) + 1

                filter.save()
                
                if filter_id:
                    filter.audit_update(audit_obj, request.user)
                else:
                    filter.audit_simple_change('++ CREATED ++', request.user)
    
                set_message(request, 'saved_filter', context={ 'filter': filter})
                set_cache_warning_message(request, website)
                return redirect('filters', website_id)
    else:
        if not filter_id:
            filter.container_element_id = '%s%s' % (filter.container_element_id[:-1], website.filters.count() + 1)
        form = FilterForm(rules, instance=filter)
        page_formset = PageInlineFormSet(instance=pagegroup)
    
    return direct_to_template(request, template='rules/filters/add_edit_filter.html', 
                              extra_context = {'form':form, 
                                               'filter':filter, 
                                               'rules':rules,
                                               'page_formset': page_formset,
                                               'preview_url': request.session.get('%s:%s:previewUrl' % (website_id,filter.name), '')})


@login_required
def de_activate_filter(request, website_id, filter_id, activate=1):
    website = get_website(request, website_id)
    filter = get_object_or_404(website.filters.filter(deleted=False), id=filter_id)

    if request.method == 'POST':
        filter.active = False if int(activate) == 0 else True
        filter.save()
        filter.audit_simple_change('%sACTIVATED' % '' if filter.active else 'DE-', request.user)
        
        summary = render_to_string('rules/filters/filter_summary.html', { 'filter': filter, 'MEDIA_URL': settings.MEDIA_URL})
        return HttpResponse(simplejson.dumps({'status': 'OK',
                                              'id': filter.id,
                                              'active': filter.active,
                                              'summary': summary}), mimetype='application/json')
    else:
        return HttpResponseBadRequest()


@login_required
def delete_filter(request, website_id, filter_id):
    website = get_website(request, website_id)
    filter = get_object_or_404(website.filters.filter(deleted=False), id=filter_id)

    dict = {'status': 'Error', 'id': filter.id}
    if request.method == 'POST':
        if filter.active == False:
            filter.deleted = True
            filter.save()
            filter.audit_simple_change('-- DELETED --', request.user)
            dict['status'] = 'OK'
        else:
            dict['status'] = 'In use'
            dict['message'] = 'The filter is active, please make inactive before deleting.'
    else:
        return HttpResponseBadRequest()
    
    return HttpResponse(simplejson.dumps(dict), mimetype='application/json')
    


copy_rule_name = re.compile(r'\[([0-9])+\]\s*')

def get_rule_types(rids, rules):
    result = []
    for rid in rids.split(','):
        if rid and rules.filter(pk=rid):
            result.append(rules.get(pk=rid).handler_choice)
    return result

@login_required
def add_edit_rule(request, website_id, rule_id=None, copy=False):
    website = get_website(request, website_id)
    rules = website.rules.all()
    if rule_id:
        rule = get_object_or_404(rules, pk=rule_id)
        if copy: 
            rule.id = None
            rule.copy_of = rule_id             
    else:
        rule = Rule(website=website)
    
    choice = 0
    handler_form = None
    if request.method == 'POST':        
        existing_rule_types = get_rule_types(request.POST.get('rids', ''), rules) 
        form = RuleForm(existing_rule_types, data=request.POST, instance=rule)
        
        if form.is_valid():
            choice = form.cleaned_data['handler_choice']
            handler_form_obj = HANDLER_FORMS[choice]
            handler_form = handler_form_obj(request.POST)
            #if hasattr(handler_form, 'override_querysets'): handler_form.override_querysets({'location_groups': location_groups})
            if handler_form.is_valid():
                handler = handler_form.save()
                rule = form.save(commit=False)
                rule.handler = handler
                rule.save()
                
                summary = render_to_string('rules/rules/rule_summary.html', { 'rule': rule, 'MEDIA_URL': settings.MEDIA_URL })
                return HttpResponse(simplejson.dumps({'status': 'OK',
                                                  'id': rule.id,
                                                  'summary': summary,}), mimetype='application/json')
        else:
            try:
                choice = int(request.POST.get('handler_choice', rule.handler_choice if rule_id else 0))
            except ValueError:
                choice = 0
            if choice:
                hfo = HANDLER_FORMS[choice]
                handler_form = hfo(request.POST)
    else:
        if copy: 
            try:
                mtchs = copy_rule_name.search(rule.name)
                if mtchs:
                    rule.name = copy_rule_name.sub( '[%s]' % (int(mtchs.groups()[0]) + 1), rule.name)
                else:
                    rule.name = '%s [2]' % (rule.name)
            except: pass
        existing_rule_types = get_rule_types(request.GET.get('rids', ''), rules)
        form = RuleForm(existing_rule_types, instance=rule)
        if rule_id:
            choice = rule.handler_choice
            hfo = HANDLER_FORMS[choice]
            handler_form = hfo(instance=rule.handler)
    
    handler_forms = {}
    for k, hf in HANDLER_FORMS.items():
        if k == choice:
            handler_forms[k] = handler_form 
        else:
            handler_forms[k] = hf() 
        if hasattr(handler_forms[k], 'coerce_data'): handler_forms[k].coerce_data()
        #if hasattr(handler_forms[k], 'override_querysets'): handler_forms[k].override_querysets({'location_groups': location_groups})
        handler_forms[k].handler_type = HANDLER_CHOICES_DICT[k]

    return direct_to_template(request, template='rules/rules/add_edit_rule_ajax.html',
                              extra_context={'form': form,  
                                             'rule': rule,
                                             'copy': copy,
                                             'orig_rule_id': rule_id,  
                                             'handler_forms': handler_forms,
                                             })

@login_required
def rules(request, website_id):
    website = get_website(request, website_id)
    return direct_to_template(request, template='rules/rules/rules.html',
                              extra_context={'rules': website.rules.all(),})

    
@login_required
def delete_rule(request, website_id, rule_id):
    website = get_website(request, website_id)
    rule = get_object_or_404(website.rules.all(), pk=rule_id)
    dict = {'status': 'Error', 'id': rule.id}
    if request.method == 'POST':
        if rule.filters.filter(deleted=False).count() == 0:
            rule.delete()
            dict['status'] = 'OK'
        else:
            dict['status'] = 'In use'
            dict['message'] = 'The rule is in use, please remove from any filters before deleting.'
    else:
        return HttpResponseBadRequest()
    
    return HttpResponse(simplejson.dumps(dict), mimetype='application/json')

@login_required
def delete_user_or_invite(request, website_id, invite_id=None, wuser_id=None):
    website = get_website(request, website_id)
    if request.method == 'POST':
        if wuser_id:
            wuser = get_object_or_404(website.authorised_users.exclude(user=website.account.owner).filter(id=wuser_id))
            wuser.delete()
        else:
            invite = get_object_or_404(website.invites.filter(id=invite_id))
            invite.delete()
        return HttpResponse(simplejson.dumps({'status': 'OK', 'wuser_id': wuser_id if wuser_id else 0, 'invite_id': invite_id if invite_id else 0, }), mimetype='application/json')
    else:
        return HttpResponseBadRequest()    


def process_invites(administered_sites, permissioning_user, account_owner, request):
    invite_qs = UserInvite.objects.filter(email_sent=False, website__in=administered_sites)
    
    invites_by_email = {}
    
    sent_mail = False
    changes_made = False
    
    for invite in invite_qs:
        if invite.email in invites_by_email:
            invites_by_email[invite.email].append(invite)
        else:
            invites_by_email[invite.email] = [invite]
    
    for email, invites in invites_by_email.items():
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            websites = ', '.join([invite.website.name for invite in invites])
            body = render_to_string('rules/admin/permission_added_email.txt', {'websites': websites, 
                                                                         'perm_user': permissioning_user, 
                                                                         'email':email, 
                                                                         'token':invites[0].token})
            subject = render_to_string('rules/admin/permission_invitation_subject.txt', {'perm_user': permissioning_user})
            send_mail(subject.splitlines()[0], body, 'landing@landing.at', [email])
            sent_mail = True
            changes_made = True
            for invite in invites:
                invite.email_sent = True
                invite.save()        
        else:
            websites = []
            for invite in invites:
                if user == permissioning_user or user == account_owner:
                    set_message(request, 'permission_change_mistake', 
                                level = 'attention',
                                context = { 'user' : user,
                                            'permissioning_user' : permissioning_user,
                                            'account_owner' : account_owner
                                             })
                elif not WebsiteUser.objects.filter(user=user, website__id=invite.website.id, level=invite.level).exists():
                    WebsiteUser.objects.filter(user=user, website__id=invite.website.id).delete() # in case there are any at a different level
                    wu = WebsiteUser(user=user, website=invite.website, level=invite.level)
                    wu.save()
                    changes_made = True
                    websites.append(invite.website.name)
                invite.delete()
            if len(websites) > 0:
                body = render_to_string('rules/admin/permission_added_email.txt', {'websites': ', '.join(websites), 'perm_user': permissioning_user, 'invitee':user})
                subject = render_to_string('rules/admin/permission_granted_subject.txt', {'perm_user': permissioning_user})
                send_mail(subject.splitlines()[0], body, 'landing@landing.at', [email])
                sent_mail = True
                
    return sent_mail, changes_made

#class BaseArticleFormSet(BaseFormSet):
#    def add_fields(self, form, index):
#        super(BaseArticleFormSet, self).add_fields(form, index)
#        form.fields["my_field"] = forms.CharField()

#ArticleFormSet = formset_factory(ArticleForm, formset=BaseArticleFormSet)

def inject_website(formset, website):
    for form in formset.forms:
        form.instance = UserInvite(website=website)


@login_required
def administer_site(request, website_id):
    if request.method == 'POST':
        website = get_website(request, website_id, min_level=ADMIN)
        account_owner = website.account.owner 
        form = UserInviteForm(request.POST, instance=UserInvite(website=website))
        
        if form.is_valid():
            audit_obj = website.audit_fields()
            form.save()
            sent, changes_made = process_invites([website.id], request.user, account_owner, request)
            
            if changes_made:    
                website.audit_update(audit_obj, request.user)
                set_message(request, 'perm_changes', context={'invitations_sent' : sent, 'website': website})
            return redirect('administer_site', website.id)
    else:
        website = get_website(request, website_id, min_level=READ_ONLY)
        account_owner = website.account.owner
        form = UserInviteForm()
    
    extra_context={'form': form,
                    'owner': account_owner,}    
    
    if request.user.accounts.all():
        account = request.user.accounts.all()[0]
        websites = Website.objects.filter(account=account)
        ups = account.user_plans.filter(end_date__isnull=True)
        user_plan = ups[0] if ups else None
        extra_context['account'] = account
        extra_context['websites'] = websites
        extra_context['user_plan'] = user_plan
            
    return direct_to_template(request, template="rules/admin/administer.html", 
                              extra_context=extra_context)

whitespace_re = re.compile('\s+')

def get_test_url(request):
    url = request.POST.get('test_url', None)
    if url:
        url = url if url.lower().startswith('http') else 'http://%s' % url
    elif getattr(request, 'is_sandbox', False):
        url = 'http://www.example.com/'
    return url

@login_required
def verify_website(request, website_id):
    website = get_website(request, website_id)
    
    if request.method == 'POST':
        url = get_test_url(request)
        parsed_url = urlparse(url)
        
        dict = {}
        
        if not parsed_url.hostname.lower().endswith(website.name.lower()):
            dict['errors'] = ['URL must be to a page in your website']
        else:
            try:
                page = urllib2.urlopen(url)
            except HTTPError, he:
                dict['errors'] = ['Error opening %s; %s' % (url, he)]
                dict['status'] = 'Error'
            except URLError, e:
                dict['errors'] = ['Error opening %s: %s' % (url, e.reason)]
                dict['status'] = 'Error'
            else:
                website.verify_url = url
                soup = BeautifulSoup(page)

                if not find_script(soup, website):
                    dict['errors'] = ['landing.at script block not found in %s' % url]
                else:
                    dict['status'] = 'Verified'
                    website.verified_date = datetime.datetime.now()
                
                website.save()
                
#                if not soup.find(id='mergeezee'):
#                    wrn = 'Container element with id "mergeezee" not found in page: filters may not operate without this.'
#                    dict['warnings'] = [wrn]
            
        return HttpResponse(simplejson.dumps(dict), mimetype='application/json')
    
    return HttpResponseBadRequest()


def find_script(soup, website):
    scripts = soup.findAll('script')
    lat_script_found = False
    snippet = whitespace_re.sub('', website.js_fragment())
    for script in scripts:
        stripped = whitespace_re.sub('', str(script))
        if snippet == stripped:
            lat_script_found = True
            script.extract()
            break
    return lat_script_found



def _check_filter(request, website):
    form = FilterForm(website.rules.all(), 
                      data=request.POST, instance=Filter(website=website))
    dict = {'status': 'OK', 'errors': []}        
    if not form.is_valid():
        dict['status'] = 'Error'
        for k, errs in form.errors.items():
            label = form.fields[k].label
            for err in errs:
                dict['errors'].append('%s: %s' % (label, err))
    
    url = get_test_url(request)    
    if not url:
        dict['status'] = 'Error'
        dict['errors'].append('You must specify the test URL. ')

    return dict, form, url

@login_required
def check_filter(request, website_id):
    website = get_website(request, website_id)
    
    if request.method == 'POST':
        dict, _, u = _check_filter(request, website)
        dict['preview_url'] = reverse("preview_filter", kwargs={"website_id": website_id})
        return HttpResponse(simplejson.dumps(dict), mimetype='application/json')
    
    return HttpResponseBadRequest()

@login_required
def preview_filter(request, website_id, filter_id=None):
    website = get_website(request, website_id)
    
    if request.method == 'POST':
        if filter_id:
            filter = website.filters.filter(deleted=False).get(id=filter_id)
            url = request.POST.get('test_url', None)
        else:
            #should already be checked
            dict, form, url = _check_filter(request, website)
            if dict['status'] == 'OK':
                filter = form.save(commit=False)
            else:
                return HttpResponseBadRequest()
        
        if getattr(request, 'is_sandbox', False):
            dict['msg_script'] = render_to_string('landing/message.js', {'filters': [filter] })
            dict['page'] = render_to_string('sandbox/preview_html.html', {'filter': filter})
            dict['filter'] = filter
        else:        
            try:
                page = urllib2.urlopen(url)
            except HTTPError, he:
                dict['errors'] = ['Error opening %s; %s' % (url, he)]
                dict['status'] = 'Error'
            except URLError, e:
                dict['errors'] = ['Error opening %s: %s' % (url, e.reason)]
                dict['status'] = 'Error'
            else:
                soup = BeautifulSoup(page)
                comments = soup.findAll(text=lambda text:isinstance(text, Comment))
                [comment.extract() for comment in comments]
                
                baseTag = soup.find('base')
                if not baseTag or len(baseTag) == 0:
                    #insert base
                    baseTag = Tag(soup, 'base')
                    baseTag['href'] = url
                    soup.find('head').insert(0, baseTag)
                
                dict['warnings'] = []
                if not find_script(soup, website):
                    dict['warnings'].append('landing.at script block not found in page: profiles will not operate without this.')
                    #scripts = soup.findAll('script')
                [script.extract() for script in soup.findAll('script')]
                    
                
                found_ids = soup.findAll(id=filter.container_element_id)
                len_founds = len(found_ids)
                if len_founds == 0:
                    dict['warnings'].append('Container element with id "%s" not found in page: this profile will not operate without this.' % (filter.container_element_id))
                elif len_founds > 1:
                    dict['warnings'].append('Container element with id "%s" found %s times in the page: profile may not operate correctly.' % (filter.container_element_id, len_founds))
    
                dict['msg_script'] = render_to_string('landing/message.js', {'filters': [filter] })
                dict['page'] = str(soup)
                dict['filter'] = filter
    
                request.session['%s:%s:previewUrl' % (website_id, filter.name)] = url
            
        return direct_to_template(request, template="rules/filters/preview_filter.html", 
                                      extra_context=dict)
    
    return HttpResponseBadRequest()

def set_cache_warning_message(request, website): 
    set_message(request, 'cache_warning', level='attention', context={'website': website})

        