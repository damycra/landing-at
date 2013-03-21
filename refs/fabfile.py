from __future__ import with_statement
from fabric.api import *
import datetime
import fabric.colors as colors
import os

weba = 'admin@web-a:2222'
webb = 'admin@web-b:2222'
redisa = 'admin@redis-a:2222'
dba = 'admin@db-a:2222'
stg = 'admin@stg:2222'


env.roledefs['web-heads'] = [weba, webb, redisa]
env.roledefs['cdn'] = [dba, redisa]
env.roledefs['manage'] = [dba]

env.roledefs['stg'] = [stg]

ips = {
    weba: {'shared': 'xxx.xxx.210.167',
           'private': '10.xxx.104.120',
           'pairs_private':'10.xxx.100.40'},
    webb: {'shared': 'xxx.xxx.210.167',
           'private': '10.xxx.100.40',
           'pairs_private':'10.xxx.104.120'},
    redisa: {'shared': 'xxx.xxx.228.30', 
           'private': '10.xxx.107.81',
           'pairs_private':'10.xxx.96.15'},
    dba: {'shared': 'xxx.xxx.228.30', 
           'private': '10.xxx.96.15',
           'pairs_private':'10.xxx.107.81'},
    stg: {'shared': 'xxx.xxx.230.15', 
           'private': '10.xxx.110.227',
          },
}

def _tar_put_untar():
    time = datetime.datetime.now().strftime('%Y%m%d%H%M')
    with cd('/tmp/export'):
        local('tar czf /tmp/refs-%s.tgz ./refs/' % time)
    put('/tmp/refs-%s.tgz' % time, '/tmp/')

    with cd('/tmp'):
        run('rm -rf /tmp/refs')
        run('tar xzf refs-%s.tgz' % time)
        run('rm /tmp/refs/initial_data.json.gz')
        if 'private' in ips[env.host_string]:
            run('perl -e "s/%%%%PRIVATE_IP_ADDRESS%%%%/%s/g" -pi $(find /tmp/refs -type f)' % ips[env.host_string]['private'] )
        if 'shared' in ips[env.host_string]:
            run('perl -e "s/%%%%SHARED_IP_ADDRESS%%%%/%s/g" -pi $(find /tmp/refs -type f)' % ips[env.host_string]['shared'] )
        if 'pairs_private' in ips[env.host_string]:
            run('perl -e "s/%%%%PAIR_PRIVATE_IP_ADDRESS%%%%/%s/g" -pi $(find /tmp/refs -type f)' % ips[env.host_string]['pairs_private'] )

    return time

def _bounce_apache():
    sudo('/etc/init.d/apache2 graceful')


def _deploy_web(time=None):
    if not time:
        time = _tar_put_untar() 
    with cd('/usr/local/landing.at/live'):
        sudo('cp -r refs old/refs.%s' % time)
        sudo('cp -r /tmp/refs ./')
    
    
@roles('web-heads')
def deploy_web():
    _deploy_web() 

    _bounce_apache()

def _manager_and_sandbox_common():
    time = _tar_put_untar()
    
    #get the local timestamps
    css_timestamp = datetime.datetime.fromtimestamp(os.stat('/tmp/export/refs/extras/root/usr/local/landing.at/cdn/admin/css/style.css').st_mtime).strftime('%Y%m%d%H%M%S')
    js_timestamp = datetime.datetime.fromtimestamp(os.stat('/tmp/export/refs/extras/root/usr/local/landing.at/cdn/admin/js/scripts.js').st_mtime).strftime('%Y%m%d%H%M%S')
    #and apply to the remote base_layout (and anything else in templates)
    run('perl -e "s/cssts=yyyymmddhhmmss/cssts=%s/g" -pi $(find /tmp/refs/templates -type f)' % css_timestamp)
    run('perl -e "s/jsts=yyyymmddhhmmss/jsts=%s/g" -pi $(find /tmp/refs/templates -type f)' % js_timestamp)
    
    return time


def _deploy_manager():
    time = _manager_and_sandbox_common()
    
    with cd('/usr/local/landing.at/manage'):
        sudo('cp -r refs old/refs.%s' % time)
        sudo('cp -r /tmp/refs ./')
    
    return time


@roles('manage')
def deploy_manager():
    _deploy_manager()
    
    _bounce_apache()

@roles('manage')
def deploy_sandbox():
    time = _manager_and_sandbox_common()

    with cd('/usr/local/landing.at/sandbox'):
        sudo('cp -r refs old/refs.%s' % time)
        sudo('cp -r /tmp/refs ./')

    _bounce_apache()
    

@roles('cdn')
def deploy_cdn():
    _tar_put_untar()

    with cd('/usr/local/landing.at/'):
        sudo('cp -r /tmp/refs/extras/root/usr/local/landing.at/cdn ./')


def deploy_config():
    _tar_put_untar()


@roles('web-heads', 'manage', 'stg')
def update_geoip():
    put('/tmp/geoip/GeoLiteCity.dat', '/tmp/')
    sudo('cp /tmp/GeoLiteCity.dat /usr/local/landing.at/geoip/')
    _bounce_apache()


@roles('stg')
def deploy_stg():
    time = _deploy_manager()
    _deploy_web(time)
    
    with cd('/usr/local/landing.at/'):
        sudo('cp -r /tmp/refs/extras/root/usr/local/landing.at/cdn ./')
    
    _bounce_apache()


@roles('web-heads', 'manage')
def diff_config():
    _tar_put_untar()
    with settings(warn_only=True):
        colors.blue('DIFF etc', bold=True)
        run('diff -r /tmp/refs/extras/root/etc /etc | grep -v "Only in /e"')
        colors.blue('DIFF usr', bold=True)
        run('diff -r /tmp/refs/extras/root/usr /usr | grep -v "Only in /u"')
        if env.host_string == weba or env.host_string == webb:
            colors.blue('DIFF heartbeat', bold=True)
            sudo('diff -r /tmp/refs/extras/root/etc/heartbeat/web /etc/heartbeat | grep -v "Only in /e"') 
        if env.host_string == dba or env.host_string == redisa:
            colors.blue('DIFF heartbeat', bold=True)
            sudo('diff -r /tmp/refs/extras/root/etc/heartbeat/db /etc/heartbeat | grep -v "Only in /e"')

