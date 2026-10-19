import datetime
import re
import sys
import time

from troveclient.apiclient import exceptions as t_exc

from nectar_tools import auth
from nectar_tools import cmd_base
from nectar_tools import config
from nectar_tools import notifier
from nectar_tools import utils


CONF = config.CONF

ACTIONS = ['report', 'notify', 'upgrade', 'announce']
DEFAULT_SUBJECT = "Nectar Research Cloud Database Service"


class ActionError(Exception):
    pass


class BackupError(ActionError):
    pass


class UpgradeError(ActionError):
    pass


class UpgradeUnavailableError(ActionError):
    pass


class TroveDatastoreUpgradesCmd(cmd_base.CmdBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.t_client = auth.get_trove_client(self.session)
        self.notifier = notifier.TaynacNotifier(
            session=self.session,
            resource_type='database',
            resource=None,
            template_dir='databases',
            subject=self.args.subject or DEFAULT_SUBJECT,
            dry_run=not self.args.no_dry_run,
        )
        self.limit = self.args.limit
        self.action = self.args.action.lower()
        if self.action not in ACTIONS:
            print(f"Action not valid, choices {','.join(ACTIONS)}")
            sys.exit(1)
        if self.action in ['notify', 'announce']:
            if not self.args.start or not self.args.end:
                print(f"--start and --end are required with {self.action}")
                sys.exit(1)
        self.template = None
        if self.args.template:
            self.template = self.args.template.removesuffix('.tmpl')
        if self.action == 'announce' and not self.template:
            print("--template is required with announce")
            sys.exit(1)

    def add_args(self):
        """Handle command-line options"""
        super().add_args()
        (
            self.parser.add_argument(
                '--start', help='Start date/time of maintenance'
            ),
        )
        (
            self.parser.add_argument(
                '--end', help='End date/time of maintenance'
            ),
        )
        self.parser.add_argument(
            '--instance', help='Only act on certain instance'
        )
        self.parser.add_argument(
            '--datastore', help='Only act on certain datastore type'
        )
        self.parser.add_argument(
            '--datastore-version-regex',
            help='Only act on certain datastore versions',
        )
        self.parser.add_argument(
            '--action',
            default='report',
            help='Action to perform: report (default), notify, upgrade or '
            'announce. report, notify and upgrade only act on instances '
            'running an outdated datastore version. announce sends '
            '--template to every instance.',
        )
        self.parser.add_argument(
            '--template',
            help='Name of the template in templates/databases to send, '
            'without the .tmpl suffix. Required with announce; with '
            'notify it overrides the per-datastore warning template.',
        )
        self.parser.add_argument(
            '--subject',
            help=f'Email subject (default: "{DEFAULT_SUBJECT}")',
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
        default_datastores = {}
        datastores = self.t_client.datastores.list()
        for ds in datastores:
            default_datastores[ds.name] = ds.default_version
        if self.args.instance:
            instances = [self.t_client.instances.get(self.args.instance)]
        else:
            instances = self.t_client.mgmt_instances.list()
        for inst in instances:
            inst = self.t_client.instances.get(inst.id)
            ds_type = inst.datastore.get('type')
            if (
                self.args.datastore
                and ds_type.lower() != self.args.datastore.lower()
            ):
                continue
            ds_version = inst.datastore.get('version')
            if self.args.datastore_version_regex and not re.search(
                self.args.datastore_version_regex, ds_version
            ):
                continue
            if self.action == 'announce':
                if self.limit and count >= self.limit:
                    print("Limit reached")
                    break
                ds_latest_version = self.t_client.datastore_versions.get(
                    ds_type, default_datastores[ds_type]
                )
                print(
                    f"Announcing to {inst.id} running {ds_type} {ds_version}"
                )
                if self.notify(inst, ds_type, ds_version, ds_latest_version):
                    count += 1
                continue
            datastore_version = self.t_client.datastore_versions.get(
                ds_type, ds_version
            )
            if default_datastores[ds_type] != datastore_version.id:
                if self.limit and count >= self.limit:
                    print("Limit reached")
                    break
                ds_latest_version = self.t_client.datastore_versions.get(
                    ds_type, default_datastores[ds_type]
                )
                used = inst.volume.get('used', 'Unknown')
                print(
                    f"Outdated datastore, {inst.id} "
                    f"running {ds_type} {ds_version}. Used space={used}GB"
                )
                if self.action == 'notify':
                    if self.notify(
                        inst, ds_type, ds_version, ds_latest_version
                    ):
                        count += 1
                elif self.action == 'upgrade':
                    try:
                        self.upgrade(inst, ds_latest_version)
                    except UpgradeError as e:
                        print(e)
                        sys.exit(1)
                    except BackupError as e:
                        print(e)
                    except UpgradeUnavailableError as e:
                        print(e)
                    else:
                        count += 1

    def notify(self, inst, ds_type, ds_version, ds_latest_version):
        """Send the instance's project a notification email.

        Uses --template when given, otherwise the per-datastore
        warning template. Returns True when a message was sent (or
        would be sent in dry-run mode) and False when the project has
        nobody to send it to.
        """
        self.notifier.resource = inst
        used = inst.volume.get('used', 'Unknown')
        stage = self.template
        if not stage:
            stage = 'warning-{}-{}'.format(
                ds_type.lower(), ds_version.split('-')[0]
            )
        project = self.k_client.projects.get(inst.tenant_id)
        context = {
            'datastore_latest_version': ds_latest_version,
            'project': project,
            'start': self.args.start,
            'end': self.args.end,
            'used': used,
            'dashboard_url': CONF.dashboard.url,
        }
        recipient, cc = utils.get_project_recipients(self.k_client, project)
        if not recipient:
            print(
                f"Instance {inst.id}: project {project.id} has no "
                "recipients, skipping"
            )
            return False
        message = self.notifier.send_message(
            stage, recipient, extra_recipients=cc, extra_context=context
        )
        print(message)
        return True

    def upgrade(self, inst, ds_latest_version):
        if inst.datastore.get('type').lower() == 'postgresql':
            current_major = inst.datastore.get('version').split('-')[0]
            new_major = ds_latest_version.name.split('-')[0]
            if current_major != new_major:
                raise UpgradeUnavailableError(
                    f"Inst: {inst.id} Can't major upgrade postgresql"
                )
        if inst.status not in ['ACTIVE', 'HEALTHY']:
            raise UpgradeUnavailableError(f"Inst in {inst.status}")
        try:
            self.t_client.databases.list(inst)
        except t_exc.BadRequest:
            print(f"Instance {inst.id} RPC communication error")
            return

        backups = self.t_client.backups.list(instance_id=inst.id)
        needs_backup = True
        for b in backups:
            if b.name == 'Pre Upgrade':
                if b.status == 'BUILDING':
                    raise BackupError("Backup Building")
                if b.status == 'COMPLETED':
                    created = datetime.datetime.strptime(
                        b.created, "%Y-%m-%dT%H:%M:%S"
                    )
                    now = datetime.datetime.utcnow()
                    diff = (now - created).total_seconds()
                    if diff < 36000:
                        needs_backup = False
                        break

        if not self.args.no_dry_run:
            if needs_backup:
                print(f"Would back up and upgrade {inst.id}")
            else:
                print(f"Would upgrade {inst.id}")
            return
        if needs_backup:
            print(f"Backing up {inst.id}")
            backup = self.t_client.backups.create(
                name="Pre Upgrade",
                instance=inst,
                description="Admin initiated backup pre upgrade",
            )
            start_time = int(time.time())
            timeout = 3600
            interval = 5
            while True:
                backup = self.t_client.backups.get(backup.id)
                if backup.status == 'COMPLETED':
                    print(
                        f"Backup for instance {inst.id} created. "
                        f"ID={backup.id}"
                    )
                    break
                elif backup.status in ['ERROR', 'FAILED']:
                    raise BackupError(f"Backup {backup.id} failed")
                if int(time.time()) - start_time >= timeout:
                    raise BackupError(
                        f"Timed out waiting for backup {backup.id}"
                    )

                print(
                    f"Backup {backup.id} in status {backup.status}, retrying"
                )
                time.sleep(interval)
        else:
            print(f"Instance {inst.id}: Skipping backup, have recent")

        print(f"Upgrading {inst.id}")
        try:
            self.t_client.instances.upgrade(inst, ds_latest_version.id)
        except Exception as e:
            print(e)
            return

        start_time = int(time.time())
        timeout = 1200
        interval = 10
        while True:
            inst = self.t_client.instances.get(inst.id)
            if inst.status in ['ACTIVE', 'HEALTHY']:
                print(f"Inst {inst.id} Upgrade complete")
                break
            elif inst.status == 'ERROR':
                raise UpgradeError(
                    f"Inst {inst.id} upgrade failed, instance in ERROR"
                )
            if int(time.time()) - start_time >= timeout:
                raise UpgradeError(
                    f"Timed out waiting for upgrade inst {inst.id}"
                )

            print(f"Inst {inst.id} in status {inst.status}, retrying")
            time.sleep(interval)


def main():
    cmd = TroveDatastoreUpgradesCmd()
    cmd.run()


if __name__ == '__main__':
    main()
