# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os

import fixtures
import mock
from oslo_config import cfg
import six

from ironic_inspector.common import ironic as ir_utils
from ironic_inspector import node_cache
from ironic_inspector.pxe_filter import dnsmasq
from ironic_inspector.test import base as test_base

CONF = cfg.CONF


class DnsmasqTestBase(test_base.BaseTest):
    def setUp(self):
        super(DnsmasqTestBase, self).setUp()
        self.driver = dnsmasq.DnsmasqFilter()


class TestDnsmasqDriverAPI(DnsmasqTestBase):
    def setUp(self):
        super(TestDnsmasqDriverAPI, self).setUp()
        self.mock__execute = self.useFixture(
            fixtures.MockPatchObject(dnsmasq, '_execute')).mock
        self.driver._sync = mock.Mock()
        self.driver._tear_down = mock.Mock()
        self.mock__purge_dhcp_hostsdir = self.useFixture(
            fixtures.MockPatchObject(dnsmasq, '_purge_dhcp_hostsdir')).mock
        self.mock_ironic = mock.Mock()
        get_client_mock = self.useFixture(
            fixtures.MockPatchObject(ir_utils, 'get_client')).mock
        get_client_mock.return_value = self.mock_ironic
        self.start_command = '/far/boo buzz -V --ack 42'
        CONF.set_override('dnsmasq_start_command', self.start_command,
                          'dnsmasq_pxe_filter')
        self.stop_command = '/what/ever'
        CONF.set_override('dnsmasq_stop_command', self.stop_command,
                          'dnsmasq_pxe_filter')

    def test_init_filter(self):
        self.driver.init_filter()

        self.mock__purge_dhcp_hostsdir.assert_called_once_with()
        self.driver._sync.assert_called_once_with(self.mock_ironic)
        self.mock__execute.assert_called_once_with(self.start_command)

    def test_sync(self):
        self.driver.init_filter()
        # NOTE(milan) init_filter performs an initial sync
        self.driver._sync.reset_mock()
        self.driver.sync(self.mock_ironic)

        self.driver._sync.assert_called_once_with(self.mock_ironic)

    def test_tear_down_filter(self):
        mock_reset = self.useFixture(
            fixtures.MockPatchObject(self.driver, 'reset')).mock
        self.driver.init_filter()
        self.driver.tear_down_filter()

        mock_reset.assert_called_once_with()

    def test_reset(self):
        self.driver.init_filter()
        # NOTE(milan) init_filter calls _base_cmd
        self.mock__execute.reset_mock()
        self.driver.reset()

        self.mock__execute.assert_called_once_with(
            self.stop_command, ignore_errors=True)


class TestMACHandlers(test_base.BaseTest):
    def setUp(self):
        super(TestMACHandlers, self).setUp()
        self.mock_listdir = self.useFixture(
            fixtures.MockPatchObject(os, 'listdir')).mock
        self.mock_stat = self.useFixture(
            fixtures.MockPatchObject(os, 'stat')).mock
        self.mock_remove = self.useFixture(
            fixtures.MockPatchObject(os, 'remove')).mock
        self.mac = 'ff:ff:ff:ff:ff:ff'
        self.dhcp_hostsdir = '/far'
        CONF.set_override('dhcp_hostsdir', self.dhcp_hostsdir,
                          'dnsmasq_pxe_filter')
        self.mock_join = self.useFixture(
            fixtures.MockPatchObject(os.path, 'join')).mock
        self.mock_join.return_value = "%s/%s" % (self.dhcp_hostsdir, self.mac)

    def test__whitelist_mac(self):
        with mock.patch.object(six.moves.builtins, 'open',
                               new=mock.mock_open()) as mock_open:
            dnsmasq._whitelist_mac(self.mac)

        mock_fd = mock_open.return_value
        self.mock_join.assert_called_once_with(self.dhcp_hostsdir, self.mac)
        mock_open.assert_called_once_with(self.mock_join.return_value, 'w', 1)
        mock_fd.write.assert_called_once_with('%s\n' % self.mac)

    def test__blacklist_mac(self):
        with mock.patch.object(six.moves.builtins, 'open',
                               new=mock.mock_open()) as mock_open:
            dnsmasq._blacklist_mac(self.mac)

        mock_fd = mock_open.return_value
        self.mock_join.assert_called_once_with(self.dhcp_hostsdir, self.mac)
        mock_open.assert_called_once_with(self.mock_join.return_value, 'w', 1)
        mock_fd.write.assert_called_once_with('%s,ignore\n' % self.mac)

    def test__get_blacklist(self):
        self.mock_listdir.return_value = [self.mac]
        self.mock_stat.return_value.st_size = len('%s,ignore\n' % self.mac)
        ret = dnsmasq._get_blacklist()

        self.assertEqual({self.mac}, ret)
        self.mock_listdir.assert_called_once_with(self.dhcp_hostsdir)
        self.mock_join.assert_called_once_with(self.dhcp_hostsdir, self.mac)
        self.mock_stat.assert_called_once_with(self.mock_join.return_value)

    def test__get_no_blacklist(self):
        self.mock_listdir.return_value = [self.mac]
        self.mock_stat.return_value.st_size = len('%s\n' % self.mac)
        ret = dnsmasq._get_blacklist()

        self.assertEqual(set(), ret)
        self.mock_listdir.assert_called_once_with(self.dhcp_hostsdir)
        self.mock_join.assert_called_once_with(self.dhcp_hostsdir, self.mac)
        self.mock_stat.assert_called_once_with(self.mock_join.return_value)

    def test__purge_dhcp_hostsdir(self):
        self.mock_listdir.return_value = [self.mac]
        dnsmasq._purge_dhcp_hostsdir()

        self.mock_listdir.assert_called_once_with(self.dhcp_hostsdir)
        self.mock_join.assert_called_once_with(self.dhcp_hostsdir, self.mac)
        self.mock_remove.assert_called_once_with('%s/%s' % (self.dhcp_hostsdir,
                                                            self.mac))


class TestSync(DnsmasqTestBase):
    def setUp(self):
        super(TestSync, self).setUp()
        self.mock__get_blacklist = self.useFixture(
            fixtures.MockPatchObject(dnsmasq, '_get_blacklist')).mock
        self.mock__whitelist_mac = self.useFixture(
            fixtures.MockPatchObject(dnsmasq, '_whitelist_mac')).mock
        self.mock__blacklist_mac = self.useFixture(
            fixtures.MockPatchObject(dnsmasq, '_blacklist_mac')).mock
        self.mock_ironic = mock.Mock()
        self.mock_utcnow = self.useFixture(
            fixtures.MockPatchObject(dnsmasq.timeutils, 'utcnow')).mock
        self.timestamp_start = datetime.datetime.utcnow()
        self.timestamp_end = (self.timestamp_start +
                              datetime.timedelta(seconds=42))
        self.mock_utcnow.side_effect = [self.timestamp_start,
                                        self.timestamp_end]
        self.mock_log = self.useFixture(
            fixtures.MockPatchObject(dnsmasq, 'LOG')).mock
        get_client_mock = self.useFixture(
            fixtures.MockPatchObject(ir_utils, 'get_client')).mock
        get_client_mock.return_value = self.mock_ironic
        self.mock_active_macs = self.useFixture(
            fixtures.MockPatchObject(node_cache, 'active_macs')).mock
        self.ironic_macs = {'new_mac', 'active_mac'}
        self.active_macs = {'active_mac'}
        self.blacklist_macs = {'gone_mac', 'active_mac'}
        self.mock__get_blacklist.return_value = self.blacklist_macs
        self.mock_ironic.port.list.return_value = [
            mock.Mock(address=address) for address in self.ironic_macs]
        self.mock_active_macs.return_value = self.active_macs

    def test__sync(self):
        self.driver._sync(self.mock_ironic)

        self.mock__whitelist_mac.assert_has_calls([mock.call('active_mac'),
                                                   mock.call('gone_mac')],
                                                  any_order=True)
        self.mock__blacklist_mac.assert_has_calls([mock.call('new_mac')],
                                                  any_order=True)
        self.mock_ironic.port.list.assert_called_once_with(limit=0,
                                                           fields=['address'])
        self.mock_active_macs.assert_called_once_with()
        self.mock__get_blacklist.assert_called_once_with()
        self.mock_log.debug.assert_has_calls([
            mock.call('Syncing the driver'),
            mock.call('The dnsmasq PXE filter was synchronized (took %s)',
                      self.timestamp_end - self.timestamp_start)
        ])


class Test_Execute(test_base.BaseTest):
    def setUp(self):
        super(Test_Execute, self).setUp()
        self.mock_execute = self.useFixture(
            fixtures.MockPatchObject(dnsmasq.processutils, 'execute')
        ).mock
        CONF.set_override('rootwrap_config', '/path/to/rootwrap.conf')
        self.rootwrap_cmd = dnsmasq._ROOTWRAP_COMMAND.format(
            rootwrap_config=CONF.rootwrap_config)
        self.useFixture(fixtures.MonkeyPatch(
            'ironic_inspector.pxe_filter.dnsmasq._ROOTWRAP_COMMAND',
            self.rootwrap_cmd))
        self.command = 'foobar baz'

    def test__execute(self):
        dnsmasq._execute(self.command)
        self.mock_execute.assert_called_once_with(
            self.command, run_as_root=True, shell=True,
            check_exit_code=True, root_helper=self.rootwrap_cmd)

    def test__execute_ignoring_errors(self):
        dnsmasq._execute(self.command, ignore_errors=True)
        self.mock_execute.assert_called_once_with(
            self.command, run_as_root=True, shell=True,
            check_exit_code=False, root_helper=self.rootwrap_cmd)

    def test__execute_empty(self):
        dnsmasq._execute()

        self.mock_execute.assert_not_called()
