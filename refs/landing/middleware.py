import logging
from django.http import HttpResponse, Http404

class ExceptionHandlingMiddleware:
    
    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            return None
        logging.error('second last chance exception caught: %s' % exception, exc_info=exception)
        return HttpResponse(status=204)