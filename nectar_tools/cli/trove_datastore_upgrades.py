from nectar_tools import auth
from nectar_tools import cmd_base
from nectar_tools import config
from nectar_tools import notifier
from nectar_tools import utils


CONF = config.CONFIG


class TroveDatastoreUpgradesCmd(cmd_base.CmdBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.t_client = auth.get_trove_client(self.session)
        self.notifier = notifier.TaynacNotifier(
            session=self.session,
            resource_type='database',
            resource=None,
            template_dir='databases',
            subject="Nectar Research Cloud Database Service",
            dry_run=not self.args.no_dry_run)

    def add_args(self):
        """Handle command-line options"""
        super().add_args()
        self.parser.add_argument('--start',
                                 help='Start date/time of maintenance',
                                 required=True)
        self.parser.add_argument('--end',
                                 help='End date/time of maintenance',
                                 required=True)
        self.parser.add_argument('--datastore',
                                 help='Only act on certain datastore')

    def run(self):
        default_datastores = {}
        datastores = self.t_client.datastores.list()
        for ds in datastores:
            default_datastores[ds.name] = ds.default_version
        for inst in self.t_client.mgmt_instances.list():
            ds_type = inst.datastore.get('type')
            if ds_type.lower() != self.args.datastore.lower():
                continue
            ds_version = inst.datastore.get('version')
            datastore_version = self.t_client.datastore_versions.get(
                ds_type, ds_version)
            if default_datastores[ds_type] != datastore_version.id:
                ds_latest_version = self.t_client.datastore_versions.get(
                    ds_type, default_datastores[ds_type])
                print(f"Outdated datastore, {inst.id} "
                      f"running {ds_type} {ds_version}")
                self.notifier.resource = inst
                stage = 'warning-%s-%s' % (ds_type.lower(),
                                           ds_version.split('-')[0])
                project = self.k_client.projects.get(inst.tenant_id)
                context = {
                    'datastore_latest_version': ds_latest_version,
                    'project': project,
                    'start': self.args.start,
                    'end': self.args.end}
                recipient, cc = utils.get_project_recipients(self.k_client,
                                                             project)
                message = self.notifier.send_message(stage, recipient,
                                                     extra_recipients=cc,
                                                     extra_context=context
                                                     )
                print(message)


def main():
    cmd = TroveDatastoreUpgradesCmd()
    cmd.run()


if __name__ == '__main__':
    main(
)
