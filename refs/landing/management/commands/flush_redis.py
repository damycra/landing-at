from django.core.management.base import BaseCommand
from optparse import make_option
import redis
from redis import Redis
from refs import settings
import logging

class Command(BaseCommand):
    help = 'Empties named redis instance'

    args ='<redis instance 1> [<redis instance 2>]'

    def handle(self, *args, **options):
        for a in args:
            logging.info('Flush %s' % a)
            _redis = redis.from_url(settings.REDIS_URL) # Redis(**settings.REDIS_DBS[a])
            _redis.flushdb()
        