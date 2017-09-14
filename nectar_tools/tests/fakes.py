from unittest import mock

from nectar_tools import allocations
from nectar_tools import exceptions


ALLOCATIONS = {
    'dummy': {'id': 1,
              'tenant_uuid': 'dummy',
              'status': 'A',
              'start_date': '2015-01-01',
              'end_date': '2016-01-01',
              'modified_time': '2015-01-02T10:10:10Z',
              'contact_email': 'fake@fake.org',
              'approver_email': 'approver@fake.org'},
    'warning1': {'id': 2,
                 'tenant_uuid': 'warning1',
                 'status': 'A',
                 'start_date': '2015-01-01',
                 'end_date': '2017-01-01',
                 'modified_time': '2015-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'warning2': {'id': 3,
                 'tenant_uuid': 'warning2',
                 'status': 'A',
                 'start_date': '2016-12-15',
                 'end_date': '2017-01-05',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'active': {'id': 4,
               'tenant_uuid': 'active',
               'status': 'A',
               'start_date': '2015-01-01',
               'end_date': '2018-01-01',
               'modified_time': '2015-01-02T10:10:10Z',
               'contact_email': 'fake@fake.org'},
    'pending1': {'id': 6,
                 'tenant_uuid': 'pending1',
                 'status': 'X',
                 'start_date': '2016-01-01',
                 'end_date': '2016-07-01',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'pending2': {'id': 7,
                 'tenant_uuid': 'pending2',
                 'status': 'J',
                 'start_date': '2016-01-01',
                 'end_date': '2017-07-01',
                 'modified_time': '2016-12-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'expired': {'id': 10,
                'tenant_uuid': 'expired',
                'status': 'A',
                'start_date': '2015-01-01',
                'end_date': '2016-07-01',
                'modified_time': '2015-01-02T10:10:10Z',
                'contact_email': 'fake@fake.org'},
}

MANAGERS = [mock.Mock(id='manager1',
                      enabled=True,
                      email='manager1@example.org'),
            mock.Mock(id='manager2',
                      enabled=True,
                      email='manager2@example.org')
        ]

MEMBERS = [mock.Mock(id='member1',
                     enabled=True,
                     email='member1@example.org'),
           mock.Mock(id='member2',
                     enabled=False,
                     email='member2@example.org'),
           mock.Mock(id='manager1',
                     enabled=True,
                     email='manager1@example.org')
       ]


class FakeProject(object):

    def __init__(self, project_id='dummy', name='MyProject',
                 domain_id='default', enabled=True, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = project_id
        self.name = name
        self.domain_id = domain_id
        self.enabled = True


class FakeAllocationManager(object):

    def __init__(self, url=None, username=None, password=None,
                 ks_session=None, *args, **kwargs):
        self.allocations = ALLOCATIONS

    def get_current_allocation(self, project_id='dummy'):
        try:
            data = self.allocations[project_id]
            if 'tenant_uuid' in data:
                data['project_id'] = data.pop('tenant_uuid')
            return allocations.Allocation(self, data, None)
        except KeyError:
            raise exceptions.AllocationDoesNotExist(project_id=project_id)


class FakeInstance(object):

    def __init__(self, id='fake', status='ACTIVE', metadata={},
                 task_state='', vm_state='ACTIVE', host='fakehost', **kwargs):
        self.id = id
        self.status = status
        self.metadata = metadata
        setattr(self, 'OS-EXT-STS:task_state', task_state)
        setattr(self, 'OS-EXT-STS:vm_state', vm_state)
        setattr(self, 'OS-EXT-SRV-ATTR:host', host)
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeImage(object):

    def __init__(self, id='fake', name='fake_archive', status='active',
                 **kwargs):
        self.id = id
        self.name = name
        self.status = status
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


class FakeVolume(object):

    def __init__(self, id='fake',
                 **kwargs):
        self.id = id
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


ALLOCATION_RESPONSE = {
    "quotas": [
        {
            "resource": "volume.volume",
            "zone": "melbourne",
            "quota": 30,
        },
        {
            "resource": "volume.volume",
            "zone": "monash",
            "quota": 100,
        },
        {
            "resource": "object.object",
            "zone": "nectar",
            "quota": 100,
        },
        {
            "resource": "database.instances",
            "zone": "nectar",
            "quota": 2,
        },
        {
            "resource": "database.volumes",
            "zone": "nectar",
            "quota": 100,
        },
    ],
    "id": 1,
    "parent_request": None,
    "status": "A",
    "status_explanation": "",
    "created_by": "0bdf024c921848c4b74d9e69af9edf08",
    "submit_date": "2015-02-26",
    "modified_time": "2015-03-11T23:50:51Z",
    "tenant_name": "Samtest2",
    "project_name": "blahdfdfdfg",
    "contact_email": "john@example.com",
    "start_date": "2015-02-26",
    "end_date": "2015-08-25",
    "estimated_project_duration": 1,
    "convert_trial_project": False,
    "primary_instance_type": "S",
    "instances": 2,
    "cores": 2,
    "core_hours": 100,
    "instance_quota": 2,
    "ram_quota": 8,
    "core_quota": 2,
    "approver_email": "bob@bob.com",
    "volume_zone": "melbourne",
    "object_storage_zone": "melbourne",
    "use_case": "dsdsds",
    "usage_patterns": "dsdsd",
    "allocation_home": "national",
    "geographic_requirements": "dssd",
    "project_id": "0e36fd26f4784e76a17ae2fb144d4e0a",
    "estimated_number_users": 1,
    "field_of_research_1": "010101",
    "for_percentage_1": 100,
    "field_of_research_2": None,
    "for_percentage_2": 0,
    "field_of_research_3": None,
    "for_percentage_3": 0,
    "nectar_support": "",
    "ncris_support": "",
    "funding_national_percent": 100,
    "funding_node": None,
    "provisioned": False
}
