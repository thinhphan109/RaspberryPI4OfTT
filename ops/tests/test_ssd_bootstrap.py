"""Installer integration uses a fake root and synthetic vendor binary, never systemd."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch,Mock

HERE=Path(__file__).resolve().parents[1]/'ssd_bootstrap'
sys.path.insert(0,str(HERE))
import bootstrap
import build

HOST=dict(schema=1,desktop_user='thinh',desktop_uid=1000,desktop_home='/home/thinh',generation='a'*32,
          root_uuid='11111111-1111',data_uuid='22222222-2222',data_mount='/srv/pi-control',camera_device='auto')


@unittest.skipUnless(sys.platform=='linux','Linux installer only')
class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name);cls.bundle=cls.base/'kit'
        archive=cls.base/'vendor.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            data=b'fixture-not-a-real-adguard-binary';member=tarfile.TarInfo('AdGuardHome/AdGuardHome');member.size=len(data);tar.addfile(member,io.BytesIO(data))
        with patch.object(build,'DNS_SHA',hashlib.sha256(archive.read_bytes()).hexdigest()):build.build(cls.bundle,archive)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.temp_root=tempfile.TemporaryDirectory();self.addCleanup(self.temp_root.cleanup);self.root=Path(self.temp_root.name)

    def install(self,modules=('dashboard','media','camera','dns')):
        with patch.object(bootstrap,'command',side_effect=AssertionError('Host command in sandbox')):
            return bootstrap.install(self.bundle,self.root,HOST,modules,True,False)

    def test_verify(self):
        manifest,catalog=bootstrap.verify_bundle(self.bundle)
        self.assertEqual(set(manifest['modules']),set(bootstrap.MANAGED))
        self.assertEqual(catalog['modules']['dns']['kind'],'managed-vendor')

    def test_dashboard_uses_bounded_threads_and_ram_heartbeat(self):
        unit=bootstrap.units('dashboard',HOST)['pi-control-dashboard.service']
        self.assertIn('--workers 1 --worker-class gthread --threads 4',unit)
        self.assertIn('--worker-connections 32',unit)
        self.assertIn('--worker-tmp-dir /dev/shm',unit)

    def test_dependency_order(self):
        _,catalog=bootstrap.verify_bundle(self.bundle)
        self.assertEqual(bootstrap.resolve_modules(['dashboard'],catalog),['network','observer','dashboard'])
        self.assertEqual(bootstrap.resolve_modules(['dashboard'],catalog,{'network':{},'observer':{}}),['dashboard'])

    def test_no_external_module_silently_installed(self):
        _,catalog=bootstrap.verify_bundle(self.bundle)
        for module in ('remote','robot','tailscale'):
            with self.assertRaises(ValueError):bootstrap.resolve_modules([module],catalog)

    def test_plan_has_no_writes(self):
        plan=bootstrap.install(self.bundle,self.root,HOST,['dashboard'])
        self.assertFalse(plan['host_mutation']);self.assertEqual(list(self.root.iterdir()),[])

    def test_full_fake_install_and_idempotence(self):
        self.install();metadata=self.root/'var/lib/pi-control/control/modules.json'
        first=metadata.read_bytes();files={str(p.relative_to(self.root)):p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        self.install();self.assertEqual(first,metadata.read_bytes())
        after={str(p.relative_to(self.root)):p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        self.assertEqual(files,after)
        self.assertEqual(len(json.loads(first)),8)
        self.assertFalse((self.root/'opt/piwifi-web').exists())
        self.assertTrue((self.root/'etc/systemd/user/pi-media-browser.service').is_symlink())

    def test_dashboard_update_does_not_touch_other_modules_and_rollback(self):
        self.install();metadata=self.root/'var/lib/pi-control/control/modules.json';before=json.loads(metadata.read_text())
        other={str(p):p.read_bytes() for p in self.root.glob('etc/systemd/**/*') if p.is_file() and not p.is_symlink() and 'dashboard' not in p.name}
        changed=self.root/'kit2';__import__('shutil').copytree(self.bundle,changed)
        source=changed/'files/dashboard/apps.json';source.write_text(source.read_text()+'\n')
        manifest=json.loads((changed/'manifest.json').read_text());key='files/dashboard/apps.json';manifest['files'][key]=hashlib.sha256(source.read_bytes()).hexdigest()
        entries={k.removeprefix('files/dashboard/'):v for k,v in manifest['files'].items() if k.startswith('files/dashboard/')}
        digest=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest();manifest['modules']['dashboard']={'source_hash':digest,'release':'v1-'+digest[:16]}
        raw=json.dumps(manifest).encode();(changed/'manifest.json').write_bytes(raw);(changed/'manifest.sha256').write_text(hashlib.sha256(raw).hexdigest())
        bootstrap.install(changed,self.root,HOST,['dashboard'],True,False)
        after=json.loads(metadata.read_text())
        self.assertNotEqual(before['dashboard']['release'],after['dashboard']['release'])
        for module in set(before)-{'dashboard'}:self.assertEqual(before[module],after[module])
        for path,data in other.items():self.assertEqual(Path(path).read_bytes(),data)
        bootstrap.rollback(changed,self.root,HOST,'dashboard',True)
        self.assertEqual(json.loads(metadata.read_text())['dashboard'],before['dashboard'])

    def test_rollback_has_no_old_release(self):
        self.install(['dashboard'])
        with self.assertRaisesRegex(ValueError,'No previous'):bootstrap.rollback(self.bundle,self.root,HOST,'dashboard')

    def test_symlink_destination_rejected(self):
        (self.root/'etc').symlink_to('/etc')
        with self.assertRaisesRegex(ValueError,'symlink'):self.install(['dashboard'])

    def test_root_sd_refused_before_mutation(self):
        with patch.object(bootstrap,'legacy_exists',return_value=False),patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap.os,'uname',return_value=Mock(machine='aarch64')),patch.object(bootstrap,'mount_info',side_effect=[dict(fstype='ext4',uuid=HOST['root_uuid'],source='/dev/mmcblk0p2'),dict(fstype='ext4',uuid=HOST['data_uuid'],source='/dev/sda3')]):
            with self.assertRaisesRegex(ValueError,'SD'):bootstrap.preflight(HOST)

    def test_wrong_mount_uuid_refused(self):
        with patch.object(bootstrap,'legacy_exists',return_value=False),patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap.os,'uname',return_value=Mock(machine='aarch64')),patch.object(bootstrap,'mount_info',side_effect=[dict(fstype='ext4',uuid='wrong',source='/dev/sda2'),dict(fstype='ext4',uuid=HOST['data_uuid'],source='/dev/sda3')]):
            with self.assertRaisesRegex(ValueError,'UUID'):bootstrap.preflight(HOST)

    def test_valid_ssd_preflight_requests_tree_with_custom_columns(self):
        mounts=[dict(fstype='ext4',uuid=HOST['root_uuid'],source='/dev/sda2'),dict(fstype='ext4',uuid=HOST['data_uuid'],source='/dev/sda3')]
        disks={'blockdevices':[dict(path='/dev/sda',size=128035676160,tran='usb',children=[dict(path='/dev/sda2'),dict(path='/dev/sda3')])]}
        with patch.object(bootstrap,'legacy_exists',return_value=False),patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap.os,'uname',return_value=Mock(machine='aarch64')),patch.object(bootstrap,'mount_info',side_effect=mounts),patch.object(bootstrap,'command',return_value=json.dumps(disks)) as command:
            result=bootstrap.preflight(HOST)
            self.assertEqual(result['root'],'/dev/sda2');self.assertIn('--tree',command.call_args.args[0])

    def test_manifest_path_traversal(self):
        for value in ('/etc/passwd','../etc','x/../../y','a\\b'):
            with self.assertRaises(ValueError):bootstrap.safe_relative(value)

    def test_source_tamper_and_extra_files_refused(self):
        for extra in (False,True):
            with tempfile.TemporaryDirectory() as temp:
                folder=Path(temp)/'kit';__import__('shutil').copytree(self.bundle,folder)
                (folder/('extra.py' if extra else 'files/dashboard/apps.json')).write_text('tampered')
                with self.assertRaises(ValueError):bootstrap.verify_bundle(folder)

    def test_failed_dashboard_upgrade_restores_previous_release(self):
        self.install(['dashboard'])
        before=json.loads((self.root/'var/lib/pi-control/control/modules.json').read_text())
        # A distinct valid build can be supplied even when configuration fails.
        changed=self.root/'failed-kit';__import__('shutil').copytree(self.bundle,changed)
        path=changed/'files/dashboard/apps.json';path.write_text(path.read_text()+'\n\n')
        manifest=json.loads((changed/'manifest.json').read_text());manifest['files']['files/dashboard/apps.json']=hashlib.sha256(path.read_bytes()).hexdigest()
        entries={k.removeprefix('files/dashboard/'):v for k,v in manifest['files'].items() if k.startswith('files/dashboard/')}
        digest=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest();manifest['modules']['dashboard']={'source_hash':digest,'release':'v1-'+digest[:16]}
        raw=json.dumps(manifest).encode();(changed/'manifest.json').write_bytes(raw);(changed/'manifest.sha256').write_text(hashlib.sha256(raw).hexdigest())
        with patch.object(bootstrap,'configure_module',side_effect=ValueError('fixture failure')):
            with self.assertRaisesRegex(ValueError,'fixture failure'):bootstrap.install(changed,self.root,HOST,['dashboard'],True,False)
        self.assertEqual(json.loads((self.root/'var/lib/pi-control/control/modules.json').read_text()),before)
        self.assertEqual((self.root/'opt/pi-control/dashboard/current').readlink().name,before['dashboard']['release'])

    def test_other_physical_disk_refused(self):
        mounts=[dict(fstype='ext4',uuid=HOST['root_uuid'],source='/dev/sda2'),dict(fstype='ext4',uuid=HOST['data_uuid'],source='/dev/sdb3')]
        disks={'blockdevices':[dict(path='/dev/sda',size=128034708480,tran='usb',children=[dict(path='/dev/sda2')]),dict(path='/dev/sdb',size=128034708480,tran='usb',children=[dict(path='/dev/sdb3')])]}
        with patch.object(bootstrap,'legacy_exists',return_value=False),patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap.os,'uname',return_value=Mock(machine='aarch64')),patch.object(bootstrap,'mount_info',side_effect=mounts),patch.object(bootstrap,'command',return_value=json.dumps(disks)):
            with self.assertRaisesRegex(ValueError,'same approved'):bootstrap.preflight(HOST)

    def test_units_capture_independence(self):
        camera=bootstrap.units('camera',HOST)['pi-control-camera.service']
        self.assertNotIn('dashboard',camera);self.assertNotIn('After=pi-control-render',camera)
        render=bootstrap.units('render',HOST)['pi-control-camera-render@.service']
        self.assertIn('CPUQuota=100%',render);self.assertIn('MemoryMax=768M',render);self.assertNotIn('WantedBy',render)

    def test_dns_new_config_ram_logs_and_private_credentials(self):
        self.install(['dns'])
        import yaml
        data=yaml.safe_load((self.root/'etc/pi-control/dns/AdGuardHome.yaml').read_text())
        self.assertEqual(data['http']['address'],'127.0.0.1:18853');self.assertFalse(data['querylog']['file_enabled'])
        self.assertTrue(data['statistics']['dir_path'].startswith('/run/'))
        secret=self.root/'home/thinh/.config/adguardhome/credentials.json'
        self.assertEqual(secret.stat().st_mode&0o777,0o600)
        self.assertEqual((self.root/'etc/NetworkManager/system-connections/pi-control-fallback.nmconnection').stat().st_mode&0o777,0o600)
