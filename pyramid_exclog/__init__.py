import sys
from pprint import pformat
from textwrap import dedent

from pyramid.tweens import EXCVIEW
from pyramid.settings import aslist
from pyramid.settings import asbool
from pyramid.util import DottedNameResolver
from pyramid.httpexceptions import WSGIHTTPException
from pyramid.security import unauthenticated_userid

resolver = DottedNameResolver(None)

PY3 = sys.version_info[0] == 3

if PY3: # pragma: no cover
    import builtins
else:
    import __builtin__ as builtins

def as_globals_list(value):
    L = []
    value = aslist(value)
    for dottedname in value:
        if dottedname in builtins.__dict__:
            if PY3: # pragma: no cover
                dottedname = 'builtins.%s' % dottedname
            else:
                dottedname = '__builtin__.%s' % dottedname
        obj = resolver.resolve(dottedname)
        L.append(obj)
    return L

def _get_url(request):
    try:
        url = request.url
    except UnicodeDecodeError:
        # do the best we can
        url = (request.host_url +
               request.environ.get('SCRIPT_NAME') +
               request.environ.get('PATH_INFO'))
        qs = request.environ.get('QUERY_STRING')
        if qs:
            url += '?' + qs
        url = 'could not decode url: %r' % url
    return url

def _get_message(request):
    url = _get_url(request)
    unauth = unauthenticated_userid(request)

    try:
        params = request.params
    except UnicodeDecodeError:
        params = 'could not decode params'

    return dedent("""\n
    %(url)s
    
    ENVIRONMENT
    
    %(env)s
    
    
    PARAMETERS
    
    %(params)s
    
    
    UNAUTHENTICATED USER
    
    %(usr)s
    
    """) % dict(url=url,
               env=pformat(request.environ),
               params=pformat(params),
               usr=unauth if unauth else '')

def _handle_error(request, getLogger, get_message):
    # save the traceback as it may get lost when we get the message.
    # _handle_error is not in the traceback, so calling sys.exc_info
    # does NOT create a circular reference
    exc_info = sys.exc_info()
    try:
        logger = getLogger('exc_logger')
        message = get_message(request)
        logger.error(message, exc_info=exc_info)
    except:
        logger.exception("Exception while logging")
    raise

def exclog_tween_factory(handler, registry):

    get = registry.settings.get

    ignored = get('exclog.ignore', (WSGIHTTPException,))
    get_message = _get_url
    if get('exclog.extra_info', False):
         get_message = _get_message
    get_message = get('exclog.get_message', get_message)

    getLogger = get('exclog.getLogger', 'logging.getLogger')
    getLogger = resolver.resolve(getLogger)

    def exclog_tween(request, getLogger=getLogger):
        # getLogger injected for testing purposes
        try:
            return handler(request)
        except ignored:
            raise
        except:
            _handle_error(request, getLogger, get_message)
            # _handle_error always raises
            raise AssertionError('Should never get here') #pragma NO COVER
    return exclog_tween

def includeme(config):
    """
    Set up am implicit :term:`tween` to log exception information that is
    generated by your Pyramid application.  The logging data will be sent to
    the Python logger named ``exc_logger``.

    This tween configured to be placed 'below' the exception view tween.  It
    will log all exceptions (even those eventually caught by a Pyramid
    exception view) except 'http exceptions' (any exception that derives from
    ``pyramid.httpexceptions.WSGIHTTPException`` such as ``HTTPFound``).  You
    can instruct ``pyramid_exclog`` to ignore custom exception types by using
    the ``excview.ignore`` configuration setting.
    """
    get = config.registry.settings.get
    ignored = as_globals_list(get('exclog.ignore',
                                  'pyramid.httpexceptions.WSGIHTTPException'))
    extra_info = asbool(get('exclog.extra_info', False))
    get_message = get('exclog.get_message', None)
    if get_message is not None:
        get_message = config.maybe_dotted(get_message)
    config.registry.settings['exclog.ignore'] = tuple(ignored)
    config.registry.settings['exclog.extra_info'] = extra_info
    config.registry.settings['exclog.get_message'] = get_message
    config.add_tween('pyramid_exclog.exclog_tween_factory', under=EXCVIEW)
