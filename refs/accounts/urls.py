from django.conf.urls.defaults import *
from django.views.generic.simple import direct_to_template
from refs.accounts.forms import EmailOrUserAuthenticationForm

urlpatterns = patterns('',
    url(r'^plans/$', 'refs.accounts.views.choose_plan', name='choose_plan'),
    url(r'^change_plan/$', 'refs.accounts.views.change_plan', name='change_plan'),
    url(r'^invoices/$', 'refs.accounts.views.show_invoices', name='show_invoices'),
    url(r'^subscribed/$', 'refs.accounts.views.subscribed', name='subscribed'),
    (r'^login/$', 'django.contrib.auth.views.login', 
        {'authentication_form' : EmailOrUserAuthenticationForm}),
    url(r'^register/(?P<token>[-0-9a-f]+)/$', 'refs.accounts.views.register_with_token', 
        {'backend' : 'refs.accounts.backends.RegistrationBackend',},
        name='register_with_token'),
    (r'^register/$', 'registration.views.register', 
        {'backend' : 'refs.accounts.backends.RegistrationBackend',}),
    url(r'^profile/$', 'refs.accounts.views.view_profile', name='user_profile'),
    url(r'^create/$', 'refs.accounts.views.create_account', name='create_account'),
    url(r'^profile/edit/$', 'refs.accounts.views.edit_profile', name='edit_user_profile'),
    url(r'^profile/password/change/$', 'refs.accounts.views.password_change', name='change_password'),
    (r'^', include('registration.backends.default.urls')),
)
