from refs.rules.models import ADMIN, RULE_EDIT, READ_ONLY 
from refs import settings

def populate_website_and_user_permissions(request):
    result = {}
    if hasattr(request, '_website'):
        result['website'] = request._website
        if request._website.id and request.user.get_profile().last_website_id != request._website.id:
            request.user.get_profile().last_website_id = request._website.id
            request.user.get_profile().save() 
    elif request.user.is_authenticated():
        website_id = request.user.get_profile().last_website_id
        if website_id > 0:
            try:
                result['website'] = request.user.authorised_websites.get(website__id=website_id).website
            except:
                request.user.get_profile().last_website_id = 0
                request.user.get_profile().save()
    
    if request.user.is_authenticated():
        if 'website' in result and result['website'].id:
            wu_qs = result['website'].authorised_users.filter(user=request.user)
            wu = wu_qs[0] if wu_qs else None
        else:
            wu = None
        result['user_perms'] = {'account_holder': request.user.accounts.count() > 0,
                                'admin': wu.level >= ADMIN if wu else False,
                                'edit': wu.level >= RULE_EDIT if wu else False,
                                'read': wu.level >= READ_ONLY if wu else False,}
    
    return result

def sandbox(request):
    return {'sandbox': settings.SANDBOX_SITE,}
