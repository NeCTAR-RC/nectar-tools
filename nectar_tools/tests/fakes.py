from unittest import mock

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient.v1 import allocations


ALLOCATIONS = {
    'dummy': {'id': 1,
              'project_id': 'dummy',
              'status': 'A',
              'start_date': '2015-01-01',
              'end_date': '2016-01-01',
              'modified_time': '2015-01-02T10:10:10Z',
              'quotas': [],
              'contact_email': 'fake@fake.org',
              'approver_email': 'approver@fake.org',
              'notifications': True},
    'no-notifications': {'id': 1,
                         'project_id': 'dummy',
                         'status': 'A',
                         'start_date': '2015-01-01',
                         'end_date': '2016-01-01',
                         'modified_time': '2015-01-02T10:10:10Z',
                         'quotas': [],
                         'contact_email': 'fake@fake.org',
                         'approver_email': 'approver@fake.org',
                         'notifications': False},
    'warning1': {'id': 2,
                 'project_id': 'warning1',
                 'status': 'A',
                 'start_date': '2015-01-01',
                 'end_date': '2017-01-01',
                 'modified_time': '2015-01-02T10:10:10Z',
                 'quotas': [],
                 'contact_email': 'fake@fake.org'},
    'warning2': {'id': 3,
                 'project_id': 'warning2',
                 'status': 'A',
                 'start_date': '2016-12-15',
                 'end_date': '2017-01-01',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'quotas': [],
                 'contact_email': 'fake@fake.org'},
    'active': {'id': 4,
               'project_id': 'active',
               'status': 'A',
               'start_date': '2015-01-01',
               'end_date': '2018-01-01',
               'modified_time': '2015-01-02T10:10:10Z',
               'quotas': [],
               'contact_email': 'fake@fake.org'},
    'pending1': {'id': 6,
                 'project_id': 'pending1',
                 'status': 'X',
                 'start_date': '2016-01-01',
                 'end_date': '2016-07-01',
                 'modified_time': '2016-01-02T10:10:10Z',
                 'quotas': [],
                 'contact_email': 'fake@fake.org'},
    'pending2': {'id': 7,
                 'project_id': 'pending2',
                 'status': 'J',
                 'start_date': '2016-01-01',
                 'end_date': '2017-07-01',
                 'modified_time': '2016-12-02T10:10:10Z',
                 'quotas': [],
                 'contact_email': 'fake@fake.org'},
    'expired': {'id': 10,
                'project_id': 'expired',
                'status': 'A',
                'start_date': '2015-01-01',
                'end_date': '2016-07-01',
                'modified_time': '2015-01-02T10:10:10Z',
                'quotas': [],
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

    def __init__(self, id='dummy', name='MyProject',
                 domain_id='default', enabled=True, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = id
        self.name = name
        self.domain_id = domain_id
        self.enabled = True

    def to_dict(self):
        return self.__dict__


class FakeAllocationManager(object):

    def __init__(self, *args, **kwargs):
        self.allocation_cache = ALLOCATIONS

    def get_current(self, project_id='dummy'):
        try:
            data = self.allocation_cache[project_id]
            return allocations.Allocation(self, data)
        except KeyError:
            raise allocation_exceptions.AllocationDoesNotExist()

    def update(self, allocation_id, **kwargs):
        allocation = self.get(allocation_id)
        for key, value in kwargs.items():
            setattr(allocation, key, value)
        return allocation

    def get(self, id):
        return allocations.Allocation(self, ALLOCATION_RESPONSE)


class FakeInstance(object):

    def __init__(self, id='fake', status='ACTIVE', metadata={},
                 task_state='', vm_state='ACTIVE', host='fakehost',
                 availability_zone='nova', **kwargs):
        self.id = id
        self.status = status
        self.metadata = metadata
        setattr(self, 'OS-EXT-AZ:availability_zone', availability_zone)
        setattr(self, 'OS-EXT-STS:task_state', task_state)
        setattr(self, 'OS-EXT-STS:vm_state', vm_state)
        setattr(self, 'OS-EXT-SRV-ATTR:host', host)
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeImage(object):

    def __init__(self, id='fake', name='fake_archive', status='active',
                 protected=False, owner='fake_owner', **kwargs):
        self.id = id
        self.name = name
        self.status = status
        self.protected = protected
        self.owner = owner
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


COMPUTE_HOMES = {'auckland': ['auckland'],
                'ersa': ['sa'],
                'intersect': ['intersect'],
                'monash': ['monash-01', 'monash-02', 'monash-03'],
                'nci': ['NCI'],
                'qcif': ['QRIScloud'],
                'swinburne': ['swinburne-01'],
                'tpac': ['tasmania', 'tasmania-s'],
                'uom': ['melbourne-qh2-uom']}


ALLOCATION_RESPONSE = {
    "quotas": [
        {
            "resource": "compute.instances",
            "zone": "nectar",
            "quota": 2,
        },
        {
            "resource": "compute.cores",
            "zone": "nectar",
            "quota": 4,
        },
        {
            "resource": "compute.ram",
            "zone": "nectar",
            "quota": 0,
        },
        {
            "resource": "volume.gigabytes",
            "zone": "melbourne",
            "quota": 30,
        },
        {
            "resource": "volume.gigabytes",
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
    "approver_email": "bob@bob.com",
    "use_case": "dsdsds",
    "usage_patterns": "dsdsd",
    "requested_allocation_home": "unassigned",
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
    "provisioned": False,
    "notifications": True,
}


def get_allocation():
    return allocations.Allocation(FakeAllocationManager(), ALLOCATION_RESPONSE)


class FakeZone(object):

    def __init__(self, id='fake', name='myproject.example.com.',
                 **kwargs):
        self.id = id
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


ZONE_SANITISING = [
    ('MyProject', 'myproject'),
    ('My_Cool_Project_Name', 'my-cool-project-name'),
    ('MyProjectMyProjectMyProjectMyProjectMyProjectMyProjectMyProjectMyProject', # noqa
     'myprojectmyprojectmyprojectmyprojectmyprojectmyprojectmyprojec'),
]

ZONE = {
    'id': '391eb5c5-2ed5-46c4-be53-faeee6a9fd01',
    'name': 'myproject.example.com.',
}

ZONE_CREATE_TRANSFER = {
    'id': '5997b0d0-2e05-4346-af51-55534d1b533a',
    'key': 't9lNRIiuXbyT',
}

ZONE_ACCEPT_TRANSFER = {
    'id': '32985174-7e25-4ac9-88a1-c1f6d55b5410',
    'status': 'COMPLETE',
}
