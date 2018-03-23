from unittest import mock

from nectar_tools import allocations
from nectar_tools import exceptions


ALLOCATIONS = {
    'dummy': {'id': 1,
              'project_id': 'dummy',
              'status': 'A',
              'start_date': '2015-01-01',
              'end_date': '2016-01-01',
              'modified_time': '2015-01-02T10:10:10Z',
              'contact_email': 'fake@fake.org',
              'approver_email': 'approver@fake.org'},
    'warning1': {'id': 2,
                 'project_id': 'warning1',
                 'status': 'A',
                 'start_date': '2015-01-01',
                 'end_date': '2017-01-01',
                 'modified_time': '2015-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'warning2': {'id': 3,
                 'project_id': 'warning2',
                 'status': 'A',
                 'start_date': '2016-12-15',
                 'end_date': '2017-01-05',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'active': {'id': 4,
               'project_id': 'active',
               'status': 'A',
               'start_date': '2015-01-01',
               'end_date': '2018-01-01',
               'modified_time': '2015-01-02T10:10:10Z',
               'contact_email': 'fake@fake.org'},
    'pending1': {'id': 6,
                 'project_id': 'pending1',
                 'status': 'X',
                 'start_date': '2016-01-01',
                 'end_date': '2016-07-01',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'pending2': {'id': 7,
                 'project_id': 'pending2',
                 'status': 'J',
                 'start_date': '2016-01-01',
                 'end_date': '2017-07-01',
                 'modified_time': '2016-12-02T10:10:10Z',
                 'contact_email': 'fake@fake.org'},
    'expired': {'id': 10,
                'project_id': 'expired',
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
                 protected=False, **kwargs):
        self.id = id
        self.name = name
        self.status = status
        self.protected = protected
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
        {
            "resource": "share.shares",
            "zone": "qld",
            "quota": 5,
        },
        {
            "resource": "share.gigabytes",
            "zone": "qld",
            "quota": 100,
        },
        {
            "resource": "share.snapshots",
            "zone": "qld",
            "quota": 5,
        },
        {
            "resource": "share.snapshot_gigabytes",
            "zone": "qld",
            "quota": 100,
        },
                {
            "resource": "share.shares",
            "zone": "monash",
            "quota": 6,
        },
        {
            "resource": "share.gigabytes",
            "zone": "monash",
            "quota": 50,
        },
        {
            "resource": "network.network",
            "zone": "nectar",
            "quota": 2,
        },
        {
            "resource": "network.floatingip",
            "zone": "nectar",
            "quota": 1,
        },
        {
            "resource": "network.router",
            "zone": "nectar",
            "quota": 2,
        },
        {
            "resource": "network.loadbalancer",
            "zone": "nectar",
            "quota": 2,
        },
    ],
    "id": 1,
    "parent_request": None,
    "status": "A",
    "status_explanation": "",
    "created_by": "0bdf024c921848c4b74d9e69af9edf08",
    "submit_date": "2015-02-26",
    "modified_time": "2015-03-11T23:50:51Z",
    "project_name": "Samtest2",
    "project_description": "blahdfdfdfg",
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

ZONE_SANITISING = [
    ('MyProject', 'myproject.test.com.'),
    ('My_Project_Name', 'my-project-name.test.com.'),
    ('MyProjectMyProjectMyProjectMyProjectMyProjectMyProjectMyProjectMyProject', 'myprojectmyprojectmyprojectmyprojectmyprojectmyprojectmyprojec.test.com.'), # noqa
]

FAKE_ZONE = {
    'id': '391eb5c5-2ed5-46c4-be53-faeee6a9fd01',
    'name': 'myproject.test.com.',
}

FAKE_ZONE_CREATE_TRANSFER = {
    'id': '5997b0d0-2e05-4346-af51-55534d1b533a',
    'key': 't9lNRIiuXbyT',
}

FAKE_ZONE_ACCEPT_TRANSFER = {
    'id': '32985174-7e25-4ac9-88a1-c1f6d55b5410',
    'status': 'COMPLETE',
}
