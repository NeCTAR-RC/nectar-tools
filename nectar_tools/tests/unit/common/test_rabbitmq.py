from unittest import mock

import requests

from nectar_tools.common import rabbitmq
from nectar_tools import test


class ManagementClientTests(test.TestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch('nectar_tools.common.rabbitmq.requests.Session')
        self.session = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.client = rabbitmq.ManagementClient(
            'https://rabbit:15671/', 'user', 'pass'
        )

    def test_init(self):
        self.assertEqual('https://rabbit:15671', self.client.url)
        self.assertEqual(('user', 'pass'), self.session.auth)

    def test_list_queues(self):
        queues = [{'name': 'q1', 'consumers': 1}]
        self.session.get.return_value.json.return_value = queues

        result = self.client.list_queues(
            'trove', columns=['name', 'consumers']
        )

        self.session.get.assert_called_once_with(
            'https://rabbit:15671/api/queues/trove',
            params={'columns': 'name,consumers'},
            timeout=60,
        )
        self.session.get.return_value.raise_for_status.assert_called_once()
        self.assertEqual(queues, result)

    def test_list_queues_encodes_vhost(self):
        self.client.list_queues('/')

        self.session.get.assert_called_once_with(
            'https://rabbit:15671/api/queues/%2F', params={}, timeout=60
        )

    def test_list_queues_error(self):
        response = self.session.get.return_value
        response.raise_for_status.side_effect = requests.HTTPError()

        self.assertRaises(requests.HTTPError, self.client.list_queues, 'trove')

    def test_delete_queue(self):
        self.client.delete_queue('trove', 'guestagent.abc', if_unused=True)

        self.session.delete.assert_called_once_with(
            'https://rabbit:15671/api/queues/trove/guestagent.abc',
            params={'if-unused': 'true'},
            timeout=60,
        )
        delete_response = self.session.delete.return_value
        delete_response.raise_for_status.assert_called_once()

    def test_delete_queue_if_empty(self):
        self.client.delete_queue('trove', 'q', if_empty=True)

        self.session.delete.assert_called_once_with(
            'https://rabbit:15671/api/queues/trove/q',
            params={'if-empty': 'true'},
            timeout=60,
        )

    def test_delete_queue_encodes_name(self):
        self.client.delete_queue('/', 'a/b c')

        self.session.delete.assert_called_once_with(
            'https://rabbit:15671/api/queues/%2F/a%2Fb%20c',
            params={},
            timeout=60,
        )

    def test_delete_queue_already_gone(self):
        response = self.session.delete.return_value
        response.status_code = 404

        self.client.delete_queue('trove', 'q')

        response.raise_for_status.assert_not_called()

    def test_delete_queue_error(self):
        response = self.session.delete.return_value
        response.status_code = 400
        response.raise_for_status.side_effect = requests.HTTPError()

        self.assertRaises(
            requests.HTTPError, self.client.delete_queue, 'trove', 'q'
        )
