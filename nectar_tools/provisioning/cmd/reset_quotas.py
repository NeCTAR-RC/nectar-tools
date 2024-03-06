import logging

from nectarallocationclient import states

from nectar_tools.expiry import expirer
from nectar_tools.provisioning.cmd import provision


LOG = logging.getLogger(__name__)


class ResetQuotasCmd(provision.ProvisionCmd):

    def reset_all(self):
        allocations = self.manager.a_client.allocations.list(
            status=states.APPROVED, provisioned=True,
            parent_request__isnull=True, managed=True)
        for allocation in allocations:
            project = self.k_client.projects.get(allocation.project_id)
            expiry_status = getattr(
                project, expirer.AllocationExpirer.STATUS_KEY, '')
            if expiry_status != '':
                LOG.warning("%s: Allocation under expiry '%s', Skipping",
                            allocation.id, expiry_status)
                continue
            try:
                self.set_quota(allocation.id)
            except Exception as e:
                LOG.exception(e)

    def add_args(self):
        """Handle command-line options"""
        super(provision.ProvisionCmd, self).add_args()
        self.parser.description = """Reset quotas for all Allocations.
        This will reset all allocations quotas to what is set in the
        allocation system"""


def main():
    cmd = ResetQuotasCmd()
    cmd.reset_all()


if __name__ == '__main__':
    main()
