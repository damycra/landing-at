from django.contrib.auth.models import User
from registration.backends.default import DefaultBackend
from registration import signals
from django.contrib import messages
from django.contrib.auth import authenticate, login
import datetime

class EmailBackend(object):
    """ Authenticates against the email field of django.contrib.auth.models.User
    
    """

    def authenticate(self, username=None, password=None):
        # Try using the user
        if username:
            for user in User.objects.filter(email__iexact=username):
                if user.check_password(password):
                    return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except object.DoesNotExist:
            return None
        

class RegistrationBackend(DefaultBackend):
    """ 
    
    """
    
    def register(self, request, **kwargs):
        """
        Register a new user account.
        
        If there is a valid token and a matching email address, create an active user and process the invites for this user.
        
        Else just create a user: no email verification at the moment.
    
        After the ``User`` is created, the signal
        ``registration.signals.user_registered`` will be sent, with
        the new ``User`` as the keyword argument ``user`` and the
        class of this backend as the sender.
        
        """
        
        username, password = kwargs['username'], kwargs['password1']
        
        token = kwargs.get('token', None)         
        if token:
            from refs.rules.models import UserInvite, WebsiteUser
            invite = UserInvite.objects.get(token=token)
            email = invite.email
            new_user = User.objects.create_user(username, email, password)

            all_invites_for_email = UserInvite.objects.filter(email=email).order_by('level')
            for inv in all_invites_for_email:
                audit_obj = inv.website.audit_fields()
                if not WebsiteUser.objects.filter(user=new_user, website__id=inv.website.id, level=inv.level).exists():
                    WebsiteUser.objects.filter(user=new_user, website__id=inv.website.id).delete()
                    wu = WebsiteUser(user=new_user, website=inv.website, level=inv.level)
                    wu.save()
                    inv.website.audit_update(audit_obj, new_user)
                inv.delete()
        else:
            email = kwargs['email']
            new_user = User.objects.create_user(username, email, password)
            
        signals.user_registered.send(sender=self.__class__,
                                 user=new_user,
                                 request=request)
        messages.info(request, 'Successfully created user%s' % (' with email address: %s' % (email) if token else ''))
            
        #now log them in too
        authed_user = authenticate(username=email, password=password)
        if authed_user is not None and authed_user.is_active:
            login(request, authed_user)
                    
        return new_user        
    
        
    def get_form_class(self, request):
        """
        Return the default form class used for user registration.
        
        """
        from refs.accounts.forms import UserRegistrationForm

        return UserRegistrationForm
    
    
    def post_registration_redirect(self, request, user):
        """
        Return the name of the URL to redirect to after successful
        user registration.
        
        """
        return ('add_website', (), {})
