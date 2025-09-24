import re
import sys

from nectar_tools import auth
from nectar_tools import cmd_base
from nectar_tools import config
from nectar_tools import notifier
from nectar_tools import utils


CONF = config.CONFIG

supported_version_re = r'v1.32|v1.33'
near_eol_version_re = r'v1.31'


class ActionError(Exception):
    pass


class BackupError(ActionError):
    pass


class UpgradeError(ActionError):
    pass


class UpgradeUnavailableError(ActionError):
    pass


def extract_k8s_info(s):
    # Extract minor version
    version_match = re.search(r'kubernetes-v\d+\.(\d+)\.\d+', s)
    minor_version = int(version_match.group(1)) if version_match else None

    # Extract location (assumes it's the part between the patch version and the next "-v")
    location_match = re.search(r'\d+\.\d+-(.*?)-v\d+', s)
    location = location_match.group(1) if location_match else None

    return minor_version, location


class MagnumDatastoreUpgradesCmd(cmd_base.CmdBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.m_client = auth.get_magnum_client(self.session)
        self.notifier = notifier.TaynacNotifier(
            session=self.session,
            resource_type='cluster',
            resource=None,
            template_dir='coe',
            subject="Action Required: Nectar Kubernetes Service",
            dry_run=not self.args.no_dry_run,
        )
        self.limit = self.args.limit
        self.action = self.args.action.lower()
        if self.action not in ['notify', 'upgrade', 'report']:
            print("Acion not valid, choices upgrade,notify")
            sys.exit(1)
        if self.action == 'notify':
            if not self.args.date:
                print("--date are required with notify")
                sys.exit(1)

        self.cluster_template_map = {}
        cluster_templates = self.m_client.cluster_templates.list()
        for ct in cluster_templates:
            if ct.hidden:
                pass
            self.cluster_template_map[ct.uuid] = ct

    def add_args(self):
        """Handle command-line options"""
        super().add_args()
        (self.parser.add_argument('--date', help='Date of maintenance'),)
        self.parser.add_argument(
            '--cluster', help='Only act on certain cluster'
        )
        self.parser.add_argument(
            '--template', help='Only act on certain template'
        )
        self.parser.add_argument(
            '--action', default='report', help='Action to perform'
        )
        self.parser.add_argument(
            '-l',
            '--limit',
            type=int,
            default=0,
            help='Only process this many eligible instances.',
        )

    def run(self):
        count = 0

        if self.args.cluster:
            clusters = [self.m_client.clusters.get(self.args.cluster)]
        else:
            clusters = self.m_client.clusters.list(detail=True)
        for cluster in clusters:
            cluster = self.m_client.clusters.get(cluster.uuid)
            cluster_template = self.m_client.cluster_templates.get(
                cluster.cluster_template_id
            )
            if 'capi_helm_chart_version' not in cluster_template.labels:
                # print("Heat upgrade not supported")
                continue
            if "DELETE" in cluster.status:
                continue
            if "CREATE_IN_PROGRESS" in cluster.status:
                continue
            if "CREATE_FAILED" in cluster.status:
                continue
            if "COMPLETE" not in cluster.status:
                print(
                    f"Cluster {cluster.name} {cluster.uuid} in state {cluster.status}"
                )
                continue
            if cluster.health_status != "HEALTHY":
                print(f"Cluster {cluster.name} {cluster.uuid} not HEALTHY")
                continue

            if not re.search(supported_version_re, cluster_template.name):
                if self.limit and count >= self.limit:
                    print("Limit reached")
                    break

                print(
                    f"Outdated cluster, {cluster.name} ({cluster.uuid}) "
                    f"running {cluster_template.name}"
                )
                if self.action == 'notify':
                    self.notify(cluster, cluster_template)
                    count += 1
                elif self.action == 'upgrade':
                    try:
                        self.upgrade(cluster, cluster_template)
                    except UpgradeError as e:
                        print(e)
                        sys.exit(1)
                    except BackupError as e:
                        print(e)
                    except UpgradeUnavailableError as e:
                        print(e)
                    else:
                        count += 1

    def notify(self, cluster, cluster_template):
        self.notifier.resource = cluster
        project = self.k_client.projects.get(cluster.project_id)
        context = {
            'cluster': cluster,
            'project': project,
            'date': self.args.date,
        }
        recipient, cc = utils.get_project_recipients(self.k_client, project)
        if re.search(near_eol_version_re, cluster_template.name):
            stage = 'near-eol-upgrade'
        else:
            stage = 'eol-upgrade'
        self.notifier.send_message(
            stage, recipient, extra_recipients=cc, extra_context=context
        )

    def upgrade(self, cluster, cluster_template):
        minor_version, location = extract_k8s_info(cluster_template.name)
        if not minor_version:
            print("ERROR no version found")
            return
        new_minor_version = int(minor_version) + 1
        new_version = (
            rf'kubernetes-v1\.{new_minor_version}\.(\d+)-{location}-v(\d+)'
        )

        matches = []

        for uuid, ct in self.cluster_template_map.items():
            found = re.match(new_version, ct.name)
            if found:
                matches.append(ct)

        if not matches:
            print("No version to upgrade to")
            return
        elif len(matches) > 1:
            print(
                "More than one version to update to %s"
                % [ct.name for ct in matches]
            )
            return
        elif matches[0].uuid == cluster_template.uuid:
            return

        new_ct = matches[0]
        if self.args.no_dry_run:
            print(f"Upgrading to {new_ct.name}")
            self.m_client.clusters.upgrade(cluster.uuid, new_ct.uuid)
        else:
            print(
                f"Would upgrade from {cluster_template.name} to {new_ct.name}"
            )
            print(
                f"openstack coe cluster upgrade {cluster.uuid} {new_ct.uuid}"
            )


def main():
    cmd = MagnumDatastoreUpgradesCmd()
    cmd.run()


if __name__ == '__main__':
    main()
