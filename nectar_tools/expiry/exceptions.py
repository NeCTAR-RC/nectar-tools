
class InvalidProject(Exception):
    pass


class InvalidProjectTrial(InvalidProject):
    pass


class InvalidProjectAllocation(InvalidProject):
    pass


class AllocationDoesNotExist(Exception):

    def __init__(self, project_id):
        self.project_id = project_id
        self.message = "Blah"


class NoUsageError(Exception):
    pass
