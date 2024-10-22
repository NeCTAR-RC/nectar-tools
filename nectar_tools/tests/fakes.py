import copy

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient.v1 import allocations

from nectar_tools.common import service_units


ALLOCATIONS = {
    'dummy': {
        'id': 1,
        'project_id': 'dummy',
        'project_name': 'dummy-name',
        'status': 'A',
        'start_date': '2015-01-01',
        'end_date': '2016-01-01',
        'modified_time': '2015-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
        'approver_email': 'approver@fake.org',
        'notifications': True,
    },
    'no-notifications': {
        'id': 11,
        'project_id': 'dummy',
        'project_name': 'dummy-name',
        'status': 'A',
        'start_date': '2015-01-01',
        'end_date': '2016-01-01',
        'modified_time': '2015-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
        'approver_email': 'approver@fake.org',
        'notifications': False,
    },
    'warning1': {
        'id': 2,
        'project_id': 'warning1',
        'project_name': 'warning1-name',
        'status': 'A',
        'start_date': '2015-01-01',
        'end_date': '2017-01-01',
        'modified_time': '2015-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'warning2': {
        'id': 3,
        'project_id': 'warning2',
        'project_name': 'warning2-name',
        'status': 'A',
        'start_date': '2016-12-15',
        'end_date': '2017-01-01',
        'modified_time': '2016-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'active': {
        'id': 4,
        'project_id': 'active',
        'project_name': 'active-name',
        'status': 'A',
        'start_date': '2015-01-01',
        'end_date': '2018-01-01',
        'modified_time': '2015-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'pending1': {
        'id': 6,
        'project_id': 'pending1',
        'project_name': 'pending1-name',
        'status': 'X',
        'start_date': '2016-01-01',
        'end_date': '2016-07-01',
        'modified_time': '2016-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'pending2': {
        'id': 7,
        'project_id': 'pending2',
        'project_name': 'pending2-name',
        'status': 'X',
        'start_date': '2016-01-01',
        'end_date': '2017-07-01',
        'modified_time': '2016-12-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'declined1': {
        'id': 8,
        'project_id': 'declined1',
        'project_name': 'declined1-name',
        'status': 'J',
        'start_date': '2016-01-01',
        'end_date': '2017-07-01',
        'modified_time': '2016-12-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'declined2': {
        'id': 9,
        'project_id': 'declined2',
        'project_name': 'declined-name',
        'status': 'J',
        'start_date': '2016-01-01',
        'end_date': '2017-07-01',
        'modified_time': '2016-11-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
    'expired': {
        'id': 10,
        'project_id': 'expired',
        'project_name': 'expired-name',
        'status': 'A',
        'start_date': '2015-01-01',
        'end_date': '2016-07-01',
        'modified_time': '2015-01-02T10:10:10Z',
        'quotas': [],
        'contact_email': 'fake@fake.org',
    },
}


class FakeUser:
    def __init__(self, id='dummy', enabled=True, email='fake@fake.com'):
        self.id = id
        self.enabled = enabled
        self.email = email
        self.name = email

    def to_dict(self):
        return copy.copy(self.__dict__)


MANAGERS = [
    FakeUser(id='manager1', enabled=True, email='manager1@example.org'),
    FakeUser(id='manager2', enabled=True, email='manager2@example.org'),
]

MEMBERS = [
    FakeUser(id='member1', enabled=True, email='member1@example.org'),
    FakeUser(id='member2', enabled=False, email='member2@example.org'),
    FakeUser(id='manager1', enabled=True, email='manager1@example.org'),
]


class FakeProject:
    def __init__(
        self,
        id='dummy',
        name='MyProject',
        domain_id='default',
        enabled=True,
        **kwargs,
    ):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = id
        self.name = name
        self.domain_id = domain_id
        self.enabled = enabled

    def to_dict(self):
        return copy.copy(self.__dict__)


class FakeProjectWithOwner:
    def __init__(self, id='dummy', name='pt-123', owner=FakeUser(), **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = id
        self.name = name
        self.owner = owner

    def to_dict(self):
        return copy.copy(self.__dict__)


class FakeAllocationManager:
    def __init__(self, *args, **kwargs):
        self.allocation_cache = ALLOCATIONS

    def get_current(self, project_id='dummy'):
        try:
            data = self.allocation_cache[project_id]
            return allocations.Allocation(self, data, loaded=True)
        except KeyError:
            raise allocation_exceptions.AllocationDoesNotExist()

    def update(self, allocation_id, **kwargs):
        allocation = self.get(allocation_id)
        for key, value in kwargs.items():
            setattr(allocation, key, value)
        return allocation

    def get(self, id):
        for data in self.allocation_cache.values():
            if data['id'] == id:
                return allocations.Allocation(self, data, loaded=True)
        raise allocation_exceptions.AllocationDoesNotExist()


class FakeAllocationManager2(FakeAllocationManager):
    def __init__(self, *args, **kwargs):
        self.allocation_cache = {"dummy": ALLOCATION_RESPONSE}


class FakeInstance:
    def __init__(
        self,
        id='fake',
        status='ACTIVE',
        metadata={},
        task_state='',
        vm_state='ACTIVE',
        host='fakehost',
        availability_zone='nova',
        locked_reason=None,
        image='ubuntu',
        **kwargs,
    ):
        self.id = id
        self.status = status
        self.metadata = metadata
        self.locked_reason = locked_reason
        self.image = image
        setattr(self, 'OS-EXT-AZ:availability_zone', availability_zone)
        setattr(self, 'OS-EXT-STS:task_state', task_state)
        setattr(self, 'OS-EXT-STS:vm_state', vm_state)
        setattr(self, 'OS-EXT-SRV-ATTR:host', host)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        return copy.copy(self.__dict__)


class FakeImage:
    def __init__(
        self,
        id='fake',
        name='fake_archive',
        status='active',
        protected=False,
        owner='fake_owner',
        **kwargs,
    ):
        self.id = id
        self.name = name
        self.status = status
        self.protected = protected
        self.owner = owner
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def items(self):
        return self.__dict__


class FakeVolume:
    def __init__(self, id='fake', **kwargs):
        self.id = id
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


class FakeStack:
    def __init__(self, id='fake', stack_status='CREATE_COMPLETE', **kwargs):
        self.id = id
        self.stack_status = stack_status
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


class FakeEnvironment:
    def __init__(self, id='fake', status='ready', **kwargs):
        self.id = id
        self.status = status
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


COMPUTE_HOMES = {
    'auckland': ['auckland'],
    'ersa': ['sa'],
    'intersect': ['intersect'],
    'monash': ['monash-01', 'monash-02', 'monash-03'],
    'nci': ['NCI'],
    'qcif': ['QRIScloud'],
    'swinburne': ['swinburne-01'],
    'tpac': ['tasmania', 'tasmania-s'],
    'uom': ['melbourne-qh2-uom'],
}


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
            "resource": "database.ram",
            "zone": "nectar",
            "quota": 8,
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
        {
            "resource": "rating.budget",
            "zone": "nectar",
            "quota": 3400,
        },
        {
            "resource": "nectar-reservation.reservation",
            "zone": "nectar",
            "quota": 10,
        },
        {
            "resource": "nectar-reservation.days",
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
    "associated_site": "uom",
    "national": True,
    "allocation_home": "national",
    "allocation_home_display": "National",
    "geographic_requirements": "dssd",
    "project_id": None,
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
    """Create a fake allocation client object outside of the normal (fake)
    manager framework.  Note that these objects don't have unique ids.
    """

    return allocations.Allocation(
        FakeAllocationManager(), ALLOCATION_RESPONSE, loaded=True
    )


class FakeZone:
    def __init__(self, id='fake', name='myproject.example.com.', **kwargs):
        self.id = id
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


ZONE_SANITISING = [
    ('MyProject', 'myproject'),
    ('My_Cool_Project_Name', 'my-cool-project-name'),
    (
        'MyProjectMyProjectMyProjectMyProjectMyProjectMyProjectMyProjectMyProject',  # noqa
        'myprojectmyprojectmyprojectmyprojectmyprojectmyprojectmyprojec',
    ),
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


class FakeSUinfo(service_units.SUinfo):
    def __init__(
        self, usage=10, budget=20, tracking_over=False, allocation=None
    ):
        if allocation is None:
            allocation = get_allocation()
        super().__init__(allocation=allocation, session=None)
        self._usage = usage
        self._budget = budget
        self.tracking_over = tracking_over

    def is_tracking_over(self):
        return self.tracking_over


class FakeResponse:
    def __init__(self, status_code=200, reason="OK"):
        self.status_code = status_code
        self.reason = reason


class FakeK8sObject:
    """This is an object that represents what the K8s client would return.
    Most of the objects returned via the API are super similar in nature, so
    we can simply use this object and chain objects together with this as the
    template.

    For example:

        annotations = {
            'hub.jupyter.org/username': 'fake',
        }
        metadata = FakeK8sObject(name='fake', annotations=annotations)
        pvc = FakeK8sObject(metadata=metadata)
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        result = {}
        for attr in self.__dict__.keys():
            value = getattr(self, attr)
            if isinstance(value, list):
                result[attr] = list(
                    map(
                        lambda x: x.to_dict() if hasattr(x, 'to_dict') else x,
                        value,
                    )
                )
            elif hasattr(value, "to_dict"):
                result[attr] = value.to_dict()
            elif isinstance(value, dict):
                result[attr] = dict(
                    map(
                        lambda item: (item[0], item[1].to_dict())
                        if hasattr(item[1], 'to_dict')
                        else item,
                        value.items(),
                    )
                )
            else:
                result[attr] = value
        return result

    def to_str(self):
        return str(self.to_dict())

    def __repr__(self):
        return self.to_str()


JUPYTERHUB_USER = {
    'name': 'fake@user.com',
    'created': '2023-01-01T00:00:00.000000Z',
    'last_activity': '2024-06-01T00:00:00.000000Z',
    'roles': ['user'],
    'groups': [],
    'pending': None,
    'server': None,
    'admin': False,
    'kind': 'user',
}
