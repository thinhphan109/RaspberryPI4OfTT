import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/'ssd_bootstrap/prepare_layout.py'
spec=importlib.util.spec_from_file_location('prepare_layout',PATH);layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)


def table():return dict(label='dos',id='0x9586d7bf',sectorsize=512,partitions=[dict(start=16384,size=1048576,type='c'),dict(start=1064960,size=12107776,type='83')])


class LayoutTests(unittest.TestCase):
    def test_exact_partition_geometry_and_alignment(self):
        plan=layout.geometry(table(),128035676160)
        self.assertEqual(plan['root_sectors']*512,40*1024**3)
        self.assertEqual(plan['data_sectors']*512,68*1024**3)
        self.assertEqual(plan['data_start'],plan['root_end']+1)
        self.assertEqual(plan['data_start']%2048,0)
        self.assertGreater(plan['unallocated_bytes'],10*1024**3)

    def test_wrong_disk_or_layout_refused(self):
        for field,value in (('label','gpt'),('id','0xcea1ee4f'),('sectorsize',4096)):
            with self.subTest(field=field),self.assertRaises(ValueError):layout.geometry(table()|{field:value},layout.CAPACITY)
        with self.assertRaises(ValueError):layout.geometry(table(),64021856256)

    def test_prepared_disk_not_formatted_again(self):
        before=table();before['partitions'].append(dict(start=84951040,size=142606336,type='83'))
        with self.assertRaisesRegex(ValueError,'do not repeat'):layout.geometry(before,layout.CAPACITY)

    def test_cmdline_removes_only_resize(self):
        before='console=serial0,115200 console=tty1 root=PARTUUID=9586d7bf-02 rootfstype=ext4 fsck.repair=yes rootwait resize cfg80211.ieee80211_regdom=VN\n'
        after=layout.cmdline_text(before)
        self.assertEqual(after.split(),[part for part in before.split() if part!='resize'])

    def test_unknown_cmdline_stops(self):
        for value in ('root=PARTUUID=cea1ee4f-02 resize','root=/dev/sda2 resize','root=PARTUUID=9586d7bf-02 resize resize','root=PARTUUID=9586d7bf-02'):
            with self.assertRaises(ValueError):layout.cmdline_text(value)

    def test_fstab_preserves_boot_and_root(self):
        before='proc /proc proc defaults 0 0\nPARTUUID=9586d7bf-01 /boot/firmware vfat defaults 0 2\nPARTUUID=9586d7bf-02 / ext4 defaults,noatime 0 1\n'
        result=layout.fstab_text(before,'11111111-1111-1111-1111-111111111111')
        self.assertTrue(result.startswith(before));self.assertIn('nofail,x-systemd.device-timeout=5s',result)
        with self.assertRaises(ValueError):layout.fstab_text(result,'22222222-2222-2222-2222-222222222222')
        with self.assertRaises(ValueError):layout.fstab_text(before.replace('9586d7bf','cea1ee4f'),'11111111-1111-1111-1111-111111111111')

    def test_never_apply_from_ssd_os(self):
        with patch.object(layout,'run',return_value='/dev/sda2') as command:
            with self.assertRaisesRegex(ValueError,'existing SD'):layout.identity(Path('/unused/smartctl'))
        self.assertEqual(command.call_count,2)
