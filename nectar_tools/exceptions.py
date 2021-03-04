
class InvalidProject(Exception):
    pass


class InvalidProjectTrial(InvalidProject):
    pass


class InvalidProjectAllocation(InvalidProject):
    pass


class AllocationDoesNotExist(Exception):

    def __init__(self, project_id):
        self.project_id = project_id


class NoUsageError(Exception):
    pass


class InvalidImage(Exception):
    pass


class TimeoutError(Exception):
    pass
