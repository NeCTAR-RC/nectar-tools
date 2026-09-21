"""Minimal client for the RabbitMQ management plugin HTTP API.

Only the small part of the API that nectar-tools needs is wrapped. See
https://www.rabbitmq.com/docs/management#http-api for the full API.
"""

import logging
from urllib import parse

import requests


LOG = logging.getLogger(__name__)


class ManagementClient:
    def __init__(self, url, username, password, timeout=60):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (username, password)

    def _url(self, *parts):
        # vhost names like '/' and queue names must be URL encoded as a
        # single path segment each
        quoted = [parse.quote(part, safe='') for part in parts]
        return '/'.join([self.url, 'api', *quoted])

    def list_queues(self, vhost, columns=None):
        """List the queues in a vhost.

        Returns the list of queue dicts as the API reports them, limited
        to ``columns`` when given.
        """
        params = {}
        if columns:
            params['columns'] = ','.join(columns)
        response = self.session.get(
            self._url('queues', vhost), params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def delete_queue(self, vhost, name, if_unused=False, if_empty=False):
        """Delete a queue.

        With ``if_unused`` or ``if_empty`` the broker refuses to delete a
        queue that has consumers or messages respectively. A queue that
        no longer exists is not an error.
        """
        params = {}
        if if_unused:
            params['if-unused'] = 'true'
        if if_empty:
            params['if-empty'] = 'true'
        response = self.session.delete(
            self._url('queues', vhost, name),
            params=params,
            timeout=self.timeout,
        )
        if response.status_code == 404:
            LOG.debug("Queue %s in vhost %s already gone", name, vhost)
            return
        response.raise_for_status()
