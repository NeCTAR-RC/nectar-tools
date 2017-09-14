from unittest import mock

from nectar_tools.allocations import exceptions


ALLOCATIONS = {
    'dummy': {'id': 1,
              'status': 'A',
              'start_date': '2015-01-01',
              'end_date': '2016-01-01',
              'modified_time': '2015-01-02T10:10:10Z',
              'contact_email': 'fake@fake.org',
              'approver_email': 'approver@fake.org'},
    'warning1': {'id': 2,
                 'status': 'A',
                 'start_date': '2015-01-01',
                 'end_date': '2017-01-01',
                 'modified_time': '2015-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'warning2': {'id': 3,
                 'status': 'A',
                 'start_date': '2016-12-15',
                 'end_date': '2017-01-05',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'active': {'id': 4,
               'status': 'A',
               'start_date': '2015-01-01',
               'end_date': '2018-01-01',
               'modified_time': '2015-01-02T10:10:10Z',
               'contact_email': 'fake@fake.org'},
    'pending1': {'id': 6,
                 'status': 'X',
                 'start_date': '2016-01-01',
                 'end_date': '2016-07-01',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'pending2': {'id': 7,
                 'status': 'J',
                 'start_date': '2016-01-01',
                 'end_date': '2017-07-01',
                 'modified_time': '2016-12-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'expired': {'id': 10,
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
                 domain_id='default', **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = project_id
        self.name = name
        self.domain_id = domain_id


class FakeAllocationManager(object):

    def __init__(self, allocations=None):
        self.allocations = ALLOCATIONS

    def get_current_allocation(self, project_id='dummy'):
        try:
            return self.allocations[project_id]
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


FAKE_ALLOCATION = {
    "quotas": [
        {
            "id": 1,
            "allocation": 1,
            "resource": "volume",
            "zone": "melbourne",
            "requested_quota": 30,
            "quota": 30,
            "units": "GB"
        },
        {
            "id": 2,
            "allocation": 1,
            "resource": "volume",
            "zone": "monash",
            "requested_quota": 100,
            "quota": 100,
            "units": "GB"
        },
        {
            "id": 3,
            "allocation": 1,
            "resource": "object",
            "zone": "nectar",
            "requested_quota": 100,
            "quota": 100,
            "units": "GB"
        },
        {
            "id": 4,
            "allocation": 1,
            "resource": "database_instances",
            "zone": "nectar",
            "requested_quota": 1,
            "quota": 2,
            "units": "Servers"
        },
        {
            "id": 5,
            "allocation": 1,
            "resource": "database_volumes",
            "zone": "nectar",
            "requested_quota": 20,
            "quota": 100,
            "units": "GB"
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
    "tenant_uuid": "0e36fd26f4784e76a17ae2fb144d4e0a",
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
    "funding_node": None
}
