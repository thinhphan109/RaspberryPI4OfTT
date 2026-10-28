"""One service registry shared by Help and the modular installer."""
import json
from pathlib import Path
import re
from runtime_config import modular


def read_catalog(path=None):
    path=path or Path(__file__).with_name('service_catalog.json')
    if path.is_symlink() or path.stat().st_size>128*1024:raise ValueError('Unsafe service registry')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema')!=1 or not isinstance(data.get('modules'),dict):raise ValueError('Invalid service registry')
    seen=set()
    for module,details in data['modules'].items():
        if not re.fullmatch('[a-z][a-z0-9-]{0,31}',module):raise ValueError('Invalid module id')
        for row in details.get('services',[]):
            if row.get('id') in seen or not re.fullmatch(r'[a-zA-Z0-9@.-]+\.(?:service|timer)',row.get('unit','')):raise ValueError('Invalid/duplicate service')
            if row.get('scope') not in ('user','system'):raise ValueError('Invalid service scope')
            for key in ('label','purpose','stop_impact','normal_inactive'):
                if not isinstance(row.get(key),str) or not 0<len(row[key])<=1000:raise ValueError('Missing service help')
            seen.add(row['id'])
    return data


def help_rows():
    result=[]
    for module,details in read_catalog()['modules'].items():
        for row in details.get('services',[]):
            if not modular() and row.get('legacy_unit') is None:continue
            result.append(dict(row,module=module,unit=row['unit'] if modular() else row['legacy_unit']))
    return result
