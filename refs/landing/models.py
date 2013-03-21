from django.db import models


class Url(models.Model):
    url = models.CharField(max_length=2048)

class PageViewRecord(models.Model):
    website_token = models.CharField(max_length=20, db_index=True)
    location = models.ForeignKey(Url, related_name='page_view_locations')
    view_date=models.DateTimeField(db_index=True)
    uid = models.IntegerField(db_index=True, default=0)

class ClientVisitStart(models.Model):
    website_token = models.CharField(max_length=20, db_index=True)
    client_identifier = models.CharField(db_index=True, max_length=40)
    visit_date=models.DateTimeField(db_index=True)

class FilterFiredRecord(models.Model):
    page_view = models.ForeignKey(PageViewRecord, related_name='fired_filters')
    filter_id = models.IntegerField(db_index=True)
    non_fire = models.BooleanField(default=False, blank=True, help_text='For a/b testing purposes')
