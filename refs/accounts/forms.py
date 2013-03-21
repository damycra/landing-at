from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.template.defaultfilters import slugify
from django import forms 
from django.utils.translation import ugettext_lazy as _
from django.forms.util import ErrorList
from refs.utils import random_token
from refs.accounts.models import Country
from django.contrib.localflavor.us import us_states
from django.forms.widgets import HiddenInput
import datetime
import string
import re
from django.core.validators import RegexValidator

password_re = re.compile(r'(?=.*[a-zA-Z].*$)(?=.*[0-9].*$).{7,}', re.IGNORECASE)
password_validator = RegexValidator(password_re, u"Must be at least 7 characters long & contain a letter and a number", 'not valid')


class EmailOrUserAuthenticationForm(AuthenticationForm):
    """
    Allow an email address to be used as a username 
    
    """
    
    username = forms.CharField(label=_("Email"), max_length=75)

STATE_CHOICES = (('', 'Please Select'),) + us_states.STATE_CHOICES

class UserProfileRegistrationForm(forms.Form):
    """
    Used when the user first registers, during the on register signal,
    so based on the initial questions asked on registering
    
    It is the ``UserRegistrationForm``'s job to check the email is unique, create
    a unique username and check that the state is filled in if required.
    
    In short, this relies on validation earlier in the request   
    
    """

    email = forms.EmailField(label=_("Email"))
    
    name = forms.CharField(max_length=30)
#    first_name = forms.CharField(max_length=30)
#    last_name = forms.CharField(max_length=30)
#    country = forms.ModelChoiceField(queryset=Country.objects.all())
#    state = forms.ChoiceField(choices=STATE_CHOICES, required=False)
    
    password1 = forms.CharField(widget=forms.PasswordInput(),
                                label=_("Password"),
                                validators=[password_validator])
#    password2 = forms.CharField(widget=forms.PasswordInput(),
#                                label=_("Password (again)"))
    email_optin = forms.BooleanField(required=False, initial=True)
#    accept_terms_conditions = forms.BooleanField(label='I accept the Terms & Conditions')


class UserRegistrationForm(UserProfileRegistrationForm):
    error_css_class = 'error'
    required_css_class = 'required'
    
    """
    Form for registering a new user account.
    
    Validates that the email is not already in use, and
    requires the password to be entered twice to catch typos. Generates
    a username based on the email
    
    Subclasses should feel free to add any additional validation they
    need, but should avoid defining a ``save()`` method -- the actual
    saving of collected user data is delegated to the active
    registration backend.
    
    """

    def clean_email(self):
        """
        Validate that the supplied email address is unique for the site.
        
        """
        if User.objects.filter(email__iexact=self.cleaned_data['email']):
            raise forms.ValidationError(_("This email address is already in use. Please supply a different email address."))
        return self.cleaned_data['email']

    def clean(self):
        """
        Verify that the values entered into the two password fields
        match. Note that an error here will end up in
        ``non_field_errors()`` because it doesn't apply to a single
        field.
        
        Verify that if country is US, a state has been chosen
        
        Verify that if there is a company id it corresponds to a 'public' company
        
        Verify that if there is a jobtitle id it corresponds to a 'public' job title
        
        Create a unique username, if all else has gone well
        
        """
        if 'password1' in self.cleaned_data and 'password2' in self.cleaned_data:
            if self.cleaned_data['password1'] != self.cleaned_data['password2']:
                self._errors['password2'] = ErrorList([u'Type the same password in both fields'])
                raise forms.ValidationError(_("The two password fields didn't match."))
        
        if 'country' in self.cleaned_data and self.cleaned_data['country'].code == 'US' and not self.cleaned_data['state']:
                self._errors['state'] = ErrorList([u'Choose a State'])
                    
        if not self._errors or len(self._errors) == 0:
            while True: 
                un = ("%s%s" % ( slugify(self.cleaned_data['email'])[:20],
                                random_token(string.ascii_letters[:26])))[:30] 
                if not User.objects.filter(username__iexact=un).exists():
                    self.cleaned_data['username'] = un
                    break;             
        
        return self.cleaned_data
        
        
class InvitedUserProfileRegistrationForm(UserRegistrationForm):
        token = forms.CharField(max_length=40)
        email = forms.EmailField(widget=HiddenInput(), required=False)
        
        def clean_email(self):
            if 'email' in self.cleaned_data:
                return super(InvitedUserProfileRegistrationForm, self).clean_email()
        
        def clean_token(self):
            from refs.rules.models import UserInvite
            try:
                invite = UserInvite.objects.get(token=self.cleaned_data['token'])
            except UserInvite.DoesNotExist:
                del self.cleaned_data['token']
                raise forms.ValidationError("Unknown token")
#            else:
#                if invite.created_date < datetime.datetime.now() - datetime.timedelta(days=8):
#                    del self.cleaned_data['token']
#                    raise forms.ValidationError("Token has expired, please ask your contact to invite you again.")
            
            return self.cleaned_data['token']
        
        def clean(self):
            self.cleaned_data = super(InvitedUserProfileRegistrationForm, self).clean()
            from refs.rules.models import UserInvite
            if 'token' in self.cleaned_data and (not 'email' in self.cleaned_data or len(self.cleaned_data['email']) == 0) \
                    and (not self._errors or len(self._errors) == 0):
                invite = UserInvite.objects.get(token=self.cleaned_data['token'])
                self.cleaned_data['email'] = invite.email
            
            return self.cleaned_data