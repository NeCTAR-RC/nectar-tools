PROJECTS = {
    'active': {'status': 'A', 'start_date': '2016-01-01', 'end_date': '2018-01-01'},
    'warning1': {'status': 'A', 'start_date': '2015-01-01', 'end_date': '2017-01-01'},
    'warning2': {'status': 'A', 'start_date': '2016-12-15', 'end_date': '2017-01-05'},
    'warning3': {'status': 'X', 'start_date': '2015-01-01', 'end_date': '2017-01-01'},
    'warning4': {'status': 'J', 'start_date': '2015-01-01', 'end_date': '2017-01-01'},
    'restricted1': {'status': 'A', 'start_date': '2016-01-01', 'end_date': '2016-07-01', 'next_step': '2017-01-10', 'expiry_status': 'warning'},
    'restricted2': {'status': 'A', 'start_date': '2016-01-01', 'end_date': '2016-07-01', 'next_step': '2016-08-01', 'expiry_status': 'warning'},
    'restricted3': {'status': 'X', 'start_date': '2016-01-01', 'end_date': '2016-07-01', 'next_step': '2016-08-01', 'expiry_status': 'warning'},
    'restricted4': {'status': 'J', 'start_date': '2016-01-01', 'end_date': '2016-07-01', 'next_step': '2016-08-01', 'expiry_status': 'warning'},
    'archiving1': {'status': 'A', 'start_date': '2016-01-01', 'end_date': '2016-07-01', 'next_step': '2016-08-01', 'expiry_status': 'restricted'},
    
    #'active': {'status': 'A', 'start_date': '2016-01-01', 'end_date': '2015-01-01'},

}


class FakeProject(object):

    def __init__(self, project_id):
        project = PROJECTS[project_id]
        for k,v in project.items():
            setattr(self, k, v)
            self.id = project_id


class FakeAllocationSession(object):

    def __init__(self, allocations):
        self.allocations = PROJECTS

    def get_pending_allocation(self, project_id):
        return self.allocations[project_id]


class FakeInstance(object):

    def __init__(self, id='fake', status='ACTIVE', metadata={},
                 task_state='', vm_state='ACTIVE'):
        self.id = id
        self.status = status
        self.metadata = metadata
        setattr(self, 'OS-EXT-STS:task_state', task_state)
        setattr(self, 'OS-EXT-STS:vm_state', vm_state)

class FakeImage(object):
    
    def __init__(self, id='fake', name='fake_archive', status='active',
                 properties={'nectar_archive': True}):
        self.id = id
        self.name = name
        self.status = status
        self.properties = properties
