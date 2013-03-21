from django.core.management.base import BaseCommand
from optparse import make_option
from refs.landing.records import process_backup_page_views, process_page_views

class Command(BaseCommand):
    help = 'Process the page view queues in redis'

    option_list = BaseCommand.option_list + (
        make_option('--backup',
            action='store_true',
            dest='backup',
            default=False,
            help='Work through the backup queue'),
        )

    def handle(self, *args, **options):
        if options['backup']:
            process_backup_page_views()
        else:
            process_page_views()
        