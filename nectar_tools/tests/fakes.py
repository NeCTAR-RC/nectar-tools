from nectar_tools.expiry import exceptions


ALLOCATIONS = {
    'dummy': {'id': 1,
              'status': 'A',
              'start_date': '2015-01-01',
              'end_date': '2016-01-01'},
    'warning1': {'id': 2,
                 'status': 'A',
                 'start_date': '2015-01-01',
                 'end_date': '2017-01-01'},
    'warning2': {'id': 3,
                 'status': 'A',
                 'start_date': '2016-12-15',
                 'end_date': '2017-01-05'},
    'active': {'id': 4,
               'status': 'A',
                 'start_date': '2015-01-01',
                 'end_date': '2018-01-01'},
    'pending1': {'id': 6,
                 'status': 'X',
                 'start_date': '2016-01-01',
                 'end_date': '2016-07-01'},
    'pending2': {'id': 7,
                 'status': 'J',
                 'start_date': '2016-01-01',
                 'end_date': '2016-07-01'},
    'expired': {'id': 10,
                 'status': 'A',
                 'start_date': '2015-01-01',
                'end_date': '2016-07-01'},
}


class FakeProject(object):

    def __init__(self, project_id='dummy', name='MyProject', **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = project_id
        self.name = name


class FakeAllocationSession(object):

    def __init__(self, allocations):
        self.allocations = ALLOCATIONS

    def get_current_allocation(self, project_id='dummy'):
        try:
            return self.allocations[project_id]
        except KeyError:
            raise exceptions.AllocationDoesNotExist(project_id=project_id)


class FakeInstance(object):

    def __init__(self, id='fake', status='ACTIVE', metadata={},
                 task_state='', vm_state='ACTIVE', host='fakehost'):
        self.id = id
        self.status = status
        self.metadata = metadata
        setattr(self, 'OS-EXT-STS:task_state', task_state)
        setattr(self, 'OS-EXT-STS:vm_state', vm_state)
        setattr(self, 'OS-EXT-SRV-ATTR:host', host)


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
