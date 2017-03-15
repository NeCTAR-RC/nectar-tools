import logging
import requests

from nectar_tools.expiry import exceptions


LOG = logging.getLogger(__name__)


class NectarAllocationSession(requests.Session):
    """Class to encapsulate the rest api endpoint with a requests session.

    """
    def __init__(self, url, username,
                 password, *args, **kwargs):
        self.api_url = url
        requests.Session.__init__(self, *args, **kwargs)
        self.auth = (username, password)

    def _api_get(self, rel_url, *args, **kwargs):
        return self.get("%s%s" % (self.api_url, rel_url), *args, **kwargs)

    def get_allocations(self, **kwargs):
        req = self._api_get('/rest_api/allocations/', params=kwargs)
        req.raise_for_status()
        return req.json()

    def get_quotas(self, allocation, resource='object', zone='nectar'):
        url = '/rest_api/quotas/?resource=%s&zone=%s' % (resource, zone)
        if allocation:
            url += '&allocation=%s' % allocation
        req = self._api_get(url)
        req.raise_for_status()
        return req.json()

    def get_current_allocation(self, project_id):
        allocations = self.get_allocations(tenant_uuid=project_id)
        # Can't filter by parent_request = None so do it here
        allocations = [x for x in allocations if not x['parent_request']]

        if len(allocations) == 1:
            return allocations[0]
        elif len(allocations) == 0:
            raise exceptions.AllocationDoesNotExist(project_id=project_id)
        else:

            raise ValueError("More than one allocation returned")
