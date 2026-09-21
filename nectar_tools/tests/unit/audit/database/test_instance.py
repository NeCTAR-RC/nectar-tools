from unittest import mock

from nectar_tools.audit.database import instance
from nectar_tools import exceptions
from nectar_tools import test


LIVE_ID = '11111111-2222-3333-4444-555555555555'
GONE_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


def fake_queue(name, consumers=0, messages=0):
    return {'name': name, 'consumers': consumers, 'messages': messages}


class GuestagentQueueInstanceIdTests(test.TestCase):
    def test_topic_queue(self):
        self.assertEqual(
            LIVE_ID,
            instance.guestagent_queue_instance_id(f'guestagent.{LIVE_ID}'),
        )

    def test_server_queue(self):
        self.assertEqual(
            LIVE_ID,
            instance.guestagent_queue_instance_id(
                f'guestagent.{LIVE_ID}.{LIVE_ID}'
            ),
        )

    def test_fanout_queue(self):
        self.assertEqual(
            LIVE_ID,
            instance.guestagent_queue_instance_id(
                f'guestagent.{LIVE_ID}_fanout_0123456789abcdef'
            ),
        )

    def test_other_queues(self):
        for name in [
            'guestagent',
            'guestagent.',
            'guestagent.not-a-uuid',
            f'guestagent.{LIVE_ID}x',
            f'guestagent_{LIVE_ID}',
            f'other.{LIVE_ID}',
            'trove-conductor',
            'trove-conductor.trove-01',
            'reply_0123456789abcdef',
        ]:
            self.assertIsNone(
                instance.guestagent_queue_instance_id(name), name
            )


class CleanStaleGuestagentQueuesTests(test.TestCase):
    def _get_auditor(self, dry_run=False, limit=0):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_nova_client'),
            mock.patch('nectar_tools.auth.get_trove_client'),
            mock.patch('nectar_tools.auth.get_cinder_client'),
            mock.patch('nectar_tools.auth.get_keystone_client'),
        ):
            auditor = instance.DatabaseInstanceAuditor(
                ks_session=None, dry_run=dry_run, limit=limit
            )
        auditor.t_client.mgmt_instances.list.return_value = [
            mock.Mock(id=LIVE_ID)
        ]
        patcher = mock.patch('nectar_tools.auth.get_trove_rabbitmq_client')
        self.rabbit = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.rabbit.list_queues.return_value = []
        return auditor

    def test_deletes_queues_of_deleted_instance(self):
        auditor = self._get_auditor()
        self.rabbit.list_queues.return_value = [
            fake_queue(f'guestagent.{LIVE_ID}'),
            fake_queue(f'guestagent.{LIVE_ID}.{LIVE_ID}'),
            fake_queue(f'guestagent.{LIVE_ID}_fanout_0123456789abcdef'),
            fake_queue(f'guestagent.{GONE_ID}', messages=3),
            fake_queue(f'guestagent.{GONE_ID}.{GONE_ID}'),
            fake_queue(f'guestagent.{GONE_ID}_fanout_fedcba9876543210'),
        ]

        auditor.clean_stale_guestagent_queues()

        self.rabbit.list_queues.assert_called_once_with(
            'trove', columns=['name', 'consumers', 'messages']
        )
        self.assertEqual(
            [
                mock.call(
                    vhost='trove',
                    name=f'guestagent.{GONE_ID}',
                    if_unused=True,
                ),
                mock.call(
                    vhost='trove',
                    name=f'guestagent.{GONE_ID}.{GONE_ID}',
                    if_unused=True,
                ),
                mock.call(
                    vhost='trove',
                    name=f'guestagent.{GONE_ID}_fanout_fedcba9876543210',
                    if_unused=True,
                ),
            ],
            self.rabbit.delete_queue.call_args_list,
        )

    def test_uses_configured_vhost(self):
        test.CONF.set_override('rabbitmq_vhost', '/', group='trove')
        auditor = self._get_auditor()
        self.rabbit.list_queues.return_value = [
            fake_queue(f'guestagent.{GONE_ID}')
        ]

        auditor.clean_stale_guestagent_queues()

        self.rabbit.list_queues.assert_called_once_with(
            '/', columns=['name', 'consumers', 'messages']
        )
        self.rabbit.delete_queue.assert_called_once_with(
            vhost='/', name=f'guestagent.{GONE_ID}', if_unused=True
        )

    def test_ignores_other_queues(self):
        auditor = self._get_auditor()
        self.rabbit.list_queues.return_value = [
            fake_queue('trove-conductor'),
            fake_queue('trove-conductor.trove-01'),
            fake_queue('reply_0123456789abcdef'),
            fake_queue('guestagent.not-a-uuid'),
        ]

        auditor.clean_stale_guestagent_queues()

        self.rabbit.delete_queue.assert_not_called()

    def test_skips_queue_with_consumers(self):
        auditor = self._get_auditor()
        self.rabbit.list_queues.return_value = [
            fake_queue(f'guestagent.{GONE_ID}', consumers=1),
        ]

        with mock.patch.object(instance, 'LOG') as mock_log:
            auditor.clean_stale_guestagent_queues()

        self.rabbit.delete_queue.assert_not_called()
        mock_log.warning.assert_called_once()

    def test_dry_run(self):
        auditor = self._get_auditor(dry_run=True)
        self.rabbit.list_queues.return_value = [
            fake_queue(f'guestagent.{GONE_ID}'),
        ]

        auditor.clean_stale_guestagent_queues()

        self.rabbit.delete_queue.assert_not_called()

    def test_delete_failure_continues(self):
        auditor = self._get_auditor()
        self.rabbit.list_queues.return_value = [
            fake_queue(f'guestagent.{GONE_ID}'),
            fake_queue(f'guestagent.{GONE_ID}.{GONE_ID}'),
        ]
        self.rabbit.delete_queue.side_effect = [Exception('boom'), None]

        with mock.patch.object(instance, 'LOG') as mock_log:
            auditor.clean_stale_guestagent_queues()

        self.assertEqual(2, self.rabbit.delete_queue.call_count)
        mock_log.exception.assert_called_once()

    def test_limit_reached(self):
        auditor = self._get_auditor(limit=1)
        self.rabbit.list_queues.return_value = [
            fake_queue(f'guestagent.{GONE_ID}'),
            fake_queue(f'guestagent.{GONE_ID}.{GONE_ID}'),
        ]

        self.assertRaises(
            exceptions.LimitReached, auditor.clean_stale_guestagent_queues
        )
        self.rabbit.delete_queue.assert_called_once()

    def test_lists_queues_before_instances(self):
        auditor = self._get_auditor()
        manager = mock.Mock()
        manager.attach_mock(self.rabbit.list_queues, 'list_queues')
        manager.attach_mock(
            auditor.t_client.mgmt_instances.list, 'list_instances'
        )

        auditor.clean_stale_guestagent_queues()

        self.assertEqual(
            ['list_queues', 'list_instances'],
            [c[0] for c in manager.mock_calls],
        )
