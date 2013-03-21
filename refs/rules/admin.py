from django.contrib import admin
from django.contrib.admin import ModelAdmin
from refs.rules.models import Website, SearchTermHandler, ReferralHandler, UserInvite, Filter,\
    Rule, TimeHandler, WebsiteUser, LocationGroup, Location, ChangeHistory,\
    ChangedValue

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


class WebsiteAdmin(ModelAdmin):
    search_fields =  ['name', 'token', 'account__owner__email']
    list_display = ('name', 'token', 'account')
    date_hierarchy = 'created_date'
    list_filter = ('deleted',)

class RuleAdmin(ModelAdmin):
    search_fields =  ['website__name',]
    list_display = ('__unicode__', 'website', 'copy_of' )

class CVInline(admin.TabularInline):
    model = ChangedValue

class ChangeHistAdmin(ModelAdmin):
    search_fields = ['changed_by__email']
    inlines = [CVInline,]
    
    

admin.site.register(ChangeHistory, ChangeHistAdmin)
admin.site.register(Website, WebsiteAdmin)
admin.site.register(WebsiteUser)
admin.site.register(Filter)
admin.site.register(UserInvite)
admin.site.register(Rule, RuleAdmin)
admin.site.register(Location)
admin.site.register(LocationGroup)
admin.site.register(TimeHandler)
admin.site.register(SearchTermHandler)
admin.site.register(ReferralHandler)
