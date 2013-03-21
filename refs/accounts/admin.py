from django.contrib import admin
from django.contrib.admin import ModelAdmin
from refs.accounts.models import UserProfile, Address, Country, Currency,\
    Account, UserPlan, PricePlan
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

#class ArticleAdmin(ModelAdmin):
#    list_display = ('title', 'publish_date', 'minimum_subscription_level')
#    list_editable = ('publish_date', 'minimum_subscription_level')
#    filter_horizontal = ('authors', 'topics', 'companies',)
#    prepopulated_fields = {"slug": ("title",)}
#    save_on_top = True
#    search_fields =  ['title', 'authors__name', 'companies__name']
#    list_filter = ('publish_date',)
#    date_hierarchy = 'publish_date'
#
#class FeaturedArticleAdmin(ModelAdmin):
#    raw_id_fields = ('article',)
#    list_filter = ('is_active',)
#    list_display = ('title', 'is_active', 'order')
#    list_editable = ('is_active', 'order',)
#    search_fields = ['title']


class UserProfileAdmin(ModelAdmin):
    list_display = ('__unicode__', 'email_optin', )
    search_fields =  ['user__last_name', 'user__email']

class CountryAdmin(ModelAdmin):
    search_fields =  ['name', 'code']
    list_filter = ('is_eu',)

class AccountAdmin(ModelAdmin):
    list_display = ('__unicode__', 'trial_period_ends')
    search_fields = ['owner__email']

admin.site.register(Account, AccountAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Country, CountryAdmin)
admin.site.register(Currency)
admin.site.register(Address)
admin.site.register(PricePlan)
admin.site.register(UserPlan)

class ExtraUserAdmin(UserAdmin):
    date_hierarchy = 'date_joined'
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'date_joined')

admin.site.unregister(User)
admin.site.register(User, ExtraUserAdmin)

