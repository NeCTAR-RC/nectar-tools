
class InvalidProject(Exception):
    pass


class InvalidProjectTrial(InvalidProject):
    pass


class AllocationDoesNotExist(Exception):

    def __init__(self, project_id):
        self.project_id = project_id
        self.message = "Blah"
