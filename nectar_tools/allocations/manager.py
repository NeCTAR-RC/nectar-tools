import datetime
import logging
import requests

from nectar_tools import exceptions

from nectar_tools.allocations import objects
from nectar_tools.allocations import states


LOG = logging.getLogger(__name__)
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


class AllocationManager(requests.Session):
    """Class to encapsulate the rest api endpoint with a requests session.

    """
    def __init__(self, url, username, password, ks_session=None, noop=False,
                 *args, **kwargs):
        self.api_url = url
        self.noop = noop
        requests.Session.__init__(self, *args, **kwargs)
        self.auth = (username, password)
        self.ks_session = ks_session

    def _api_get(self, rel_url, *args, **kwargs):
        return self.get("%s%s" % (self.api_url, rel_url), *args, **kwargs)

    def _api_patch(self, rel_url, data):
        return self.patch("%s%s" % (self.api_url, rel_url), data)

    def get_allocations(self, **kwargs):
        req = self._api_get('/rest_api/allocations/', params=kwargs)
        req.raise_for_status()
        allocations = []
        for data in req.json():
            if 'tenant_uuid' in data:
                data['project_id'] = data.pop('tenant_uuid')
            allocations.append(objects.Allocation(self, data, self.ks_session,
                                                  noop=self.noop))
        return allocations

    def get_allocation(self, allocation_id):
        req = self._api_get('/rest_api/allocations/%s/' % allocation_id)
        req.raise_for_status()
        data = req.json()

        if 'tenant_uuid' in data:
            data['project_id'] = data.pop('tenant_uuid')
        return objects.Allocation(self, data, self.ks_session, noop=self.noop)

    def get_quotas(self, **kwargs):
        req = self._api_get('/rest_api/quotas/', params=kwargs)
        req.raise_for_status()
        return req.json()

    def get_current_allocation(self, **kwargs):
        if 'project_id' in kwargs:
            kwargs['tenant_uuid'] = kwargs.pop('project_id')
        allocations = self.get_allocations(**kwargs)
        # Can't filter by parent_request = None so do it here
        allocations = [x for x in allocations if not x.parent_request]

        if len(allocations) == 1:
            return allocations[0]
        elif len(allocations) == 0:
            raise exceptions.AllocationDoesNotExist(project_id=None)
        else:
            ids = [x['id'] for x in allocations]
            raise ValueError("More than one allocation returned: %s" % ids)

    def get_last_approved_allocation(self, **kwargs):
        if 'project_id' in kwargs:
            kwargs['tenant_uuid'] = kwargs.pop('project_id')
        allocations = self.get_allocations(status=states.APPROVED, **kwargs)
        youngest = None
        for allocation in allocations:
            allocation.modified_time = datetime.datetime.strptime(
                allocation.modified_time, DATETIME_FORMAT)
            if youngest is None or allocation.modified_time > \
                                          youngest.modified_time:
                youngest = allocation

        return youngest

    def update_allocation(self, allocation_id, **kwargs):
        if 'project_id' in kwargs:
            kwargs['tenant_uuid'] = kwargs.pop('project_id')

        req = self._api_patch('/rest_api/allocations/%s/' % allocation_id,
                              data=kwargs)
        req.raise_for_status()
