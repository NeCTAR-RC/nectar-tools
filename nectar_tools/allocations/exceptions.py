
class AllocationDoesNotExist(Exception):

    def __init__(self, project_id):
        self.project_id = project_id
