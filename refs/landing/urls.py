from django.conf.urls.defaults import *

urlpatterns = patterns('refs.landing.views',
    url(r'^v1/msg.js$', 'get_messages', name='get_messages' ),
)


handler404 = 'refs.landing.views.bare_404'