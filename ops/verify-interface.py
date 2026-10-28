"""Read-only authenticated HTTP/HTML smoke checks for the shared dashboard UI.

Run on Pi with sudo. Does not click controls, change settings or start camera.
This checks structure/resources; it does not replace a visual browser review.
"""
from collections import Counter
from html.parser import HTMLParser
import http.cookiejar
import json
from pathlib import Path
import urllib.parse
import urllib.request


class Node:
    def __init__(self,tag='',attrs=(),parent=None):
        self.tag=tag;self.attrs=dict(attrs);self.parent=parent;self.children=[];self.text=''
    def all(self,tag=None):
        return [node for child in self.children for node in [child,*child.all()] if tag is None or node.tag==tag]
    def inside(self,tag):
        node=self.parent
        while node:
            if node.tag==tag:return True
            node=node.parent
        return False


class DOM(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr','path','circle','rect','line','polyline','ellipse','use'}
    def __init__(self,html):
        super().__init__();self.root=Node();self.current=self.root;self.feed(html)
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs,self.current);self.current.children.append(node)
        if tag not in self.VOID:self.current=node
    def handle_startendtag(self,tag,attrs):
        node=Node(tag,attrs,self.current);self.current.children.append(node)
    def handle_endtag(self,tag):
        node=self.current
        while node.parent:
            if node.tag==tag:self.current=node.parent;return
            node=node.parent
    def handle_data(self,data):self.current.text+=data


def main():
    env=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines()
             if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:18765'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    form=urllib.parse.urlencode({'username':env['PIWIFI_USER'],'password':env['PIWIFI_PASS']}).encode()
    with client.open(base+'/login',data=form,timeout=20) as response:html=response.read().decode('utf-8')
    nodes=DOM(html).root.all()
    ids=Counter(node.attrs['id'] for node in nodes if 'id' in node.attrs)
    assert not [ident for ident,count in ids.items() if count>1], 'Duplicate DOM IDs'
    by_id={node.attrs['id']:node for node in nodes if 'id' in node.attrs}
    pages={'overview','network','apps','media','audio','camera','storage','gpio','activity'}
    views={node.attrs['id']:node for node in nodes if 'view-section' in node.attrs.get('class','')}
    assert set(views)==pages
    assert {node.attrs.get('data-tab') for node in nodes if 'data-tab' in node.attrs}==pages
    assert {node.attrs.get('data-help-page') for node in nodes if 'data-help-page' in node.attrs}==pages
    topics=[node for node in nodes if 'data-help-topic' in node.attrs]
    assert {node.attrs['data-help-topic'] for node in topics}==pages
    assert all('hidden' in node.attrs for node in topics),'Help must start hidden'
    for page,view in views.items():
        assert len(view.all('h1'))==1, page
        assert any(node.attrs.get('data-help-page')==page for node in view.all()),page
    for node in nodes:
        if node.tag=='form' and node.attrs.get('method','').lower()=='post':
            assert any(child.attrs.get('name')=='csrf' for child in node.all('input')),'Missing form CSRF'
        if node.tag in ('input','button','select') and node.inside('details'):
            raise AssertionError('Functional control hidden inside details')
    assert by_id['ui-help'].tag=='dialog' and by_id['ui-help'].attrs.get('aria-labelledby')=='ui-help-title'
    assert by_id['ui-skip'].attrs['href']=='#main-content'
    assert by_id['main-content'].attrs['tabindex']=='-1'
    assert by_id['media-toggle'].inside('article') and not by_id['media-toggle'].inside('details')
    assert by_id['camera-mode'].tag=='select'
    assert 'hidden' in by_id['camera-position-settings'].attrs
    assert by_id['gpio-board'].attrs.get('aria-label')
    scripts=[node.attrs.get('src','') for node in nodes if node.tag=='script' and node.attrs.get('src')]
    assert next(i for i,s in enumerate(scripts) if 'interface.js' in s)<next(i for i,s in enumerate(scripts) if 'dashboard.js' in s)
    assert next(i for i,s in enumerate(scripts) if 'charts.js' in s)<next(i for i,s in enumerate(scripts) if 'hardware.js' in s)
    resources=scripts+[node.attrs['href'] for node in nodes if node.tag=='link' and node.attrs.get('rel')=='stylesheet']
    for resource in resources:
        with client.open(base+resource,timeout=15) as response:
            assert response.status==200
            assert len(response.read())>20
    print(json.dumps(dict(ok=True,pages=len(views),unique_ids=len(ids),resources=len(resources),checks=[
        'authenticated HTML','9 page/navigation/help pairs','one heading per view','unique DOM IDs',
        'POST form CSRF','functional controls outside details','modal labels','skip link',
        'conditional calibration','chart/script order','all JS/CSS resources HTTP200']),ensure_ascii=False))


if __name__=='__main__':main()
