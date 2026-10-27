"""New AdGuard configuration only; never copies legacy credentials or filters."""
import json
from pathlib import Path
import secrets
import subprocess


def configure(base,root,config,write,links):
    import bcrypt
    import yaml
    user=config['desktop_user'];uid=config['desktop_uid'];home=config['desktop_home']
    credential=home+'/.config/adguardhome/credentials.json'
    path=root/credential.lstrip('/')
    settings='/etc/pi-control/dns/AdGuardHome.yaml'
    existing=root/settings.lstrip('/')
    if not existing.exists():
        if path.exists():raise ValueError('Partial DNS setup: credentials exist without configuration')
        credentials={'username':'admin','password':secrets.token_urlsafe(24)}
        data={'schema_version':34,'http':{'address':'127.0.0.1:18853','session_ttl':'24h'},
              'users':[{'name':'admin','password':bcrypt.hashpw(credentials['password'].encode(),bcrypt.gensalt()).decode()}],
              'auth_attempts':5,'block_auth_min':15,'language':'en','theme':'auto',
              'dns':{'bind_hosts':['127.0.0.1'],'port':53,'upstream_dns':['https://cloudflare-dns.com/dns-query'],
                     'bootstrap_dns':['1.1.1.1','1.0.0.1'],'ratelimit':100,'use_private_ptr_resolvers':False,'resolve_clients':False,'cache_size':4194304},
              'filtering':{'protection_enabled':True,'filtering_enabled':True,'blocking_mode':'null_ip','filters_update_interval':24},
              'filters':[{'enabled':True,'url':'https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt','name':'AdGuard DNS filter','id':1}],
              'whitelist_filters':[],'user_rules':[],'dhcp':{'enabled':False},'tls':{'enabled':False},
              'querylog':{'enabled':True,'file_enabled':False,'size_memory':2000,'interval':'24h','dir_path':'/run/adguardhome/querylog'},
              'statistics':{'enabled':True,'interval':'24h','dir_path':'/run/adguardhome/statistics'},
              'clients':{'runtime_sources':{'whois':False,'arp':False,'rdns':False,'dhcp':False,'hosts':False},'persistent':[]},
              'log':{'enabled':True,'file':'','verbose':False}}
        write(root,settings,yaml.safe_dump(data,sort_keys=False),0o600)
        write(root,credential,json.dumps(credentials),0o600,uid)
    (root/'var/lib/pi-control/dns').mkdir(parents=True,exist_ok=True,mode=0o700)
    links(root,'/opt/adguardhome/AdGuardHome','/opt/pi-control/dns/current/AdGuardHome')
    links(root,'/opt/adguardhome/work','/var/lib/pi-control/dns')
    links(root,'/etc/adguardhome','/etc/pi-control/dns')
    write(root,'/etc/NetworkManager/dispatcher.d/90-pi-control-dns',
          '#!/bin/sh\ncase "$2" in up|dhcp4-change|down) /usr/local/sbin/piwifi-dns-sync ;; esac\n',0o755)
    if root==Path('/'):
        import os
        for parent in (Path(home)/'.config',Path(home)/'.config/adguardhome'):
            os.chown(parent,uid,-1)
        subprocess.run(['/opt/adguardhome/AdGuardHome','-c',settings,'-w','/var/lib/pi-control/dns','--check-config'],check=True,capture_output=True,timeout=30)
