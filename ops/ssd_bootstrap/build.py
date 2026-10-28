#!/usr/bin/env python3
"""Build a secret-free, hash-verified Linux deployment kit from explicit sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
APP=REPO/'pi-control'
URL='https://github.com/AdguardTeam/AdGuardHome/releases/download/v0.107.79/AdGuardHome_linux_arm64.tar.gz'
DNS_SHA='3f7893c18e8aaadc456d0452839190561c306ca95175a2254958be80a769c1ae'
# The reviewed upstream digest is asserted separately by tests before packaging.


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output,vendor=None):
    if output.exists():raise ValueError('Output must be a new directory')
    output.mkdir(parents=True)
    catalog=json.loads((APP/'service_catalog.json').read_text(encoding='utf-8'))
    modules={}
    for name,spec in catalog['modules'].items():
        if spec['kind'] not in ('managed','managed-vendor'):continue
        folder=output/'files'/name;folder.mkdir(parents=True)
        recipe=hashlib.sha256((HERE/'bootstrap.py').read_bytes()+(HERE/'vendor_dns.py').read_bytes()).hexdigest()
        (folder/'installer-recipe.sha256').write_text(recipe+'\n')
        for value in spec['files']:
            source=APP/value
            members=[source] if source.is_file() else sorted(source.rglob('*'))
            for path in members:
                if path.is_symlink():raise ValueError('Source symlink not allowed')
                if not path.is_file():continue
                if '__pycache__' in path.parts or path.suffix in ('.pyc','.tmp'):continue
                target=folder/path.relative_to(APP);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(path.read_bytes())
        if name=='dashboard':
            apps=[dict(id='dashboard',name='Pi Control',description='Dashboard và API',service='pi-control-dashboard',port=18765,path='/',public_url=None),
                  dict(id='adguard',name='AdGuard Home',description='DNS lọc tên miền',service='adguardhome',loopback=True,port=18853,path='/',public_url=None)]
            (folder/'apps.json').write_text(json.dumps(apps,ensure_ascii=False),encoding='utf-8')
        if name=='dns':
            archive=vendor or output/'AdGuardHome.tar.gz'
            if vendor is None:
                with urllib.request.urlopen(URL,timeout=60) as response,archive.open('xb') as stream:
                    shutil.copyfileobj(response,stream,1024*1024)
            if archive.stat().st_size>60*1024*1024 or digest(archive)!=DNS_SHA:raise ValueError('AdGuard vendor checksum mismatch')
            with tarfile.open(archive,'r:gz') as tar:
                candidates=[m for m in tar.getmembers() if m.name in ('AdGuardHome/AdGuardHome','./AdGuardHome/AdGuardHome')]
                if len(candidates)!=1:raise ValueError('Missing/duplicate AdGuard binary')
                member=candidates[0]
                if not member.isfile() or member.size>100*1024*1024:raise ValueError('Invalid AdGuard binary')
                (folder/'AdGuardHome').write_bytes(tar.extractfile(member).read())
                for filename in ('LICENSE.txt','README.md'):
                    found=[m for m in tar.getmembers() if m.name in ('AdGuardHome/'+filename,'./AdGuardHome/'+filename)]
                    if found:
                        if len(found)!=1 or not found[0].isfile() or found[0].size>1024*1024:raise ValueError('Invalid vendor documentation')
                        (folder/filename).write_bytes(tar.extractfile(found[0]).read())
            if vendor is None:archive.unlink()
        entries={str(p.relative_to(folder)).replace('\\','/'):digest(p) for p in sorted(folder.rglob('*')) if p.is_file()}
        source_hash=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest()
        modules[name]=dict(source_hash=source_hash,release='v1-'+source_hash[:16],contract=1)
    for name in ('bootstrap.py','vendor_dns.py','storage_plan.py'):
        (output/name).write_bytes((HERE/name).read_bytes())
    (output/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    history=sorted((REPO/'ops/migration').glob('deploy-history-legacy-sd-*.json'))[-1]
    for path in (history,history.with_suffix('.json.sha256')):(output/path.name).write_bytes(path.read_bytes())
    files={str(p.relative_to(output)).replace('\\','/'):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    manifest=dict(schema=1,modules=modules,files=files,vendor=dict(adguard_version='0.107.79',archive_sha256=DNS_SHA))
    raw=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    (output/'manifest.json').write_bytes(raw)
    (output/'manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--vendor',type=Path)
    args=parser.parse_args();result=build(args.output,args.vendor)
    print(json.dumps({'modules':list(result['modules']),'files':len(result['files']),'output':str(args.output)}))
