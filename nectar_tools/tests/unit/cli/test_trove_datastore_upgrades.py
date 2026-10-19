import argparse
from types import SimpleNamespace
from unittest import mock

from nectar_tools.cli import trove_datastore_upgrades as tdu
from nectar_tools import test
from nectar_tools.tests import fakes


# Datastore version name -> version id, per datastore type. The default
# version of each datastore is the newest one.
VERSIONS = {
    'mysql': {'5.7': 'v-mysql-5.7', '8.0': 'v-mysql-8.0'},
    'postgresql': {'11': 'v-pg-11', '16': 'v-pg-16'},
}
DEFAULTS = {'mysql': 'v-mysql-8.0', 'postgresql': 'v-pg-16'}


def fake_instance(id, ds_type='mysql', ds_version='8.0', tenant_id='proj'):
    return SimpleNamespace(
        id=id,
        status='HEALTHY',
        datastore={'type': ds_type, 'version': ds_version},
        volume={'size': 10, 'used': 4},
        tenant_id=tenant_id,
    )


def get_version(ds_type, name_or_id):
    """Stand-in for datastore_versions.get, by name or by id."""
    for name, vid in VERSIONS[ds_type].items():
        if name_or_id in (name, vid):
            return SimpleNamespace(id=vid, name=name)
    raise KeyError(name_or_id)


class TroveDatastoreUpgradesCmdTests(test.TestCase):
    def _make_cmd(self, action='report', template=None, limit=0, **args):
        cmd = tdu.TroveDatastoreUpgradesCmd.__new__(
            tdu.TroveDatastoreUpgradesCmd
        )
        defaults = {
            'start': 'START',
            'end': 'END',
            'instance': None,
            'datastore': None,
            'datastore_version_regex': None,
            'no_dry_run': False,
        }
        cmd.args = argparse.Namespace(**{**defaults, **args})
        cmd.action = action
        cmd.template = template
        cmd.limit = limit
        cmd.t_client = mock.Mock()
        cmd.k_client = mock.Mock()
        cmd.notifier = mock.Mock()
        return cmd

    def _setup_trove(self, cmd, instances):
        by_id = {inst.id: inst for inst in instances}
        cmd.t_client.datastores.list.return_value = [
            SimpleNamespace(name=name, default_version=vid)
            for name, vid in DEFAULTS.items()
        ]
        cmd.t_client.mgmt_instances.list.return_value = instances
        cmd.t_client.instances.get.side_effect = lambda id: by_id[id]
        cmd.t_client.datastore_versions.get.side_effect = get_version

    def _mixed_instances(self):
        return [
            fake_instance('current-mysql', 'mysql', '8.0'),
            fake_instance('old-mysql', 'mysql', '5.7'),
            fake_instance('current-pg', 'postgresql', '16'),
        ]

    def test_announce_notifies_every_instance(self):
        cmd = self._make_cmd(action='announce', template='maintenance')
        instances = self._mixed_instances()
        self._setup_trove(cmd, instances)

        with mock.patch.object(cmd, 'notify', return_value=True) as notify:
            cmd.run()

        self.assertEqual(3, notify.call_count)
        notified = [call.args[0] for call in notify.call_args_list]
        self.assertEqual(instances, notified)
        # Each call gets the datastore's default (latest) version.
        for call in notify.call_args_list:
            inst, ds_type, ds_version, latest = call.args
            self.assertEqual(inst.datastore['type'], ds_type)
            self.assertEqual(inst.datastore['version'], ds_version)
            self.assertEqual(DEFAULTS[ds_type], latest.id)

    def test_announce_respects_limit(self):
        cmd = self._make_cmd(
            action='announce', template='maintenance', limit=2
        )
        instances = self._mixed_instances()
        self._setup_trove(cmd, instances)

        with mock.patch.object(cmd, 'notify', return_value=True) as notify:
            cmd.run()

        self.assertEqual(2, notify.call_count)
        notified = [call.args[0] for call in notify.call_args_list]
        self.assertEqual(instances[:2], notified)

    def test_announce_skipped_instances_do_not_count_towards_limit(self):
        cmd = self._make_cmd(
            action='announce', template='maintenance', limit=1
        )
        instances = self._mixed_instances()
        self._setup_trove(cmd, instances)

        with mock.patch.object(
            cmd, 'notify', side_effect=[False, True, True]
        ) as notify:
            cmd.run()

        # The first instance had nobody to notify, so it does not use up
        # the limit; the second does.
        self.assertEqual(2, notify.call_count)

    def test_announce_honours_datastore_filter(self):
        cmd = self._make_cmd(
            action='announce', template='maintenance', datastore='PostgreSQL'
        )
        instances = self._mixed_instances()
        self._setup_trove(cmd, instances)

        with mock.patch.object(cmd, 'notify', return_value=True) as notify:
            cmd.run()

        notify.assert_called_once()
        self.assertEqual(instances[2], notify.call_args.args[0])

    def test_announce_single_instance(self):
        cmd = self._make_cmd(
            action='announce', template='maintenance', instance='old-mysql'
        )
        instances = self._mixed_instances()
        self._setup_trove(cmd, instances)

        with mock.patch.object(cmd, 'notify', return_value=True) as notify:
            cmd.run()

        notify.assert_called_once()
        self.assertEqual(instances[1], notify.call_args.args[0])
        cmd.t_client.mgmt_instances.list.assert_not_called()

    def test_notify_only_outdated_instances(self):
        cmd = self._make_cmd(action='notify')
        instances = self._mixed_instances()
        self._setup_trove(cmd, instances)

        with mock.patch.object(cmd, 'notify', return_value=True) as notify:
            cmd.run()

        notify.assert_called_once()
        self.assertEqual(instances[1], notify.call_args.args[0])

    def test_notify_counts_towards_limit(self):
        cmd = self._make_cmd(action='notify', limit=1)
        instances = [
            fake_instance('old-mysql', 'mysql', '5.7'),
            fake_instance('old-pg', 'postgresql', '11'),
        ]
        self._setup_trove(cmd, instances)

        with mock.patch.object(cmd, 'notify', return_value=True) as notify:
            cmd.run()

        notify.assert_called_once()
        self.assertEqual(instances[0], notify.call_args.args[0])

    def test_report_does_not_notify(self):
        cmd = self._make_cmd(action='report')
        self._setup_trove(cmd, self._mixed_instances())

        with mock.patch.object(cmd, 'notify') as notify:
            cmd.run()

        notify.assert_not_called()
        cmd.notifier.send_message.assert_not_called()


class NotifyTests(test.TestCase):
    def _make_cmd(self, template=None):
        cmd = tdu.TroveDatastoreUpgradesCmd.__new__(
            tdu.TroveDatastoreUpgradesCmd
        )
        cmd.args = argparse.Namespace(start='START', end='END')
        cmd.template = template
        cmd.k_client = mock.Mock()
        cmd.notifier = mock.Mock()
        self.project = fakes.FakeProject(id='proj', name='My Project')
        cmd.k_client.projects.get.return_value = self.project
        return cmd

    def _latest(self, name='8.0'):
        return SimpleNamespace(id=f'v-mysql-{name}', name=name)

    @mock.patch.object(tdu.utils, 'get_project_recipients')
    def test_notify_uses_template_override(self, get_recipients):
        get_recipients.return_value = ('owner@example.com', ['cc@example.com'])
        cmd = self._make_cmd(template='trove-upgrade-maintenance')
        inst = fake_instance('db1', 'mysql', '8.0')
        latest = self._latest()

        sent = cmd.notify(inst, 'mysql', '8.0', latest)

        self.assertTrue(sent)
        self.assertEqual(inst, cmd.notifier.resource)
        cmd.k_client.projects.get.assert_called_once_with('proj')
        get_recipients.assert_called_once_with(cmd.k_client, self.project)
        cmd.notifier.send_message.assert_called_once_with(
            'trove-upgrade-maintenance',
            'owner@example.com',
            extra_recipients=['cc@example.com'],
            extra_context={
                'datastore_latest_version': latest,
                'project': self.project,
                'start': 'START',
                'end': 'END',
                'used': 4,
                'dashboard_url': tdu.CONF.dashboard.url,
            },
        )

    @mock.patch.object(tdu.utils, 'get_project_recipients')
    def test_notify_default_template_from_datastore(self, get_recipients):
        get_recipients.return_value = ('owner@example.com', [])
        cmd = self._make_cmd()
        inst = fake_instance('db1', 'postgresql', '11-ubuntu')

        sent = cmd.notify(inst, 'PostgreSQL', '11-ubuntu', self._latest('16'))

        self.assertTrue(sent)
        stage = cmd.notifier.send_message.call_args.args[0]
        self.assertEqual('warning-postgresql-11', stage)

    @mock.patch.object(tdu.utils, 'get_project_recipients')
    def test_notify_skips_project_without_recipients(self, get_recipients):
        get_recipients.return_value = (None, [])
        cmd = self._make_cmd(template='trove-upgrade-maintenance')
        inst = fake_instance('db1')

        sent = cmd.notify(inst, 'mysql', '8.0', self._latest())

        self.assertFalse(sent)
        cmd.notifier.send_message.assert_not_called()
