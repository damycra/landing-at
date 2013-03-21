from django.core.management.base import BaseCommand
from optparse import make_option
from refs.landing.records import process_website_updates, refresh_cache_for_all_websites

class Command(BaseCommand):
    help = 'Updates website cache in redis based on update queue: optionally check and update the cache for all websites'

    option_list = BaseCommand.option_list + (
        make_option('--full',
            action='store_true',
            dest='full_refresh',
            default=False,
            help='Check and refresh all websites'),
        )

    def handle(self, *args, **options):
        if options['full_refresh']:
            refresh_cache_for_all_websites()
        else:
            process_website_updates()
        