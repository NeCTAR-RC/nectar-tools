from nectar_tools import auth
from nectar_tools import cmd_base


class WarreMaintenance(cmd_base.CmdBase):
    def add_args(self):
        """Handle command-line options"""
        super().add_args()
        self.parser.description = 'Adds maintenance for all flavors'

        self.parser.add_argument('--date', help='Date', required=True)

    def run(self):
        client = auth.get_warre_client()
        flavors = client.flavors.list(all_projects=True)
        date = self.args.date
        start = f'{date} 00:00'
        end = f'{date} 23:59'
        for flavor in flavors:
            try:
                client.reservations.create(
                    flavor_id=flavor.id,
                    start=start,
                    end=end,
                    instance_count=flavor.slots,
                )
                print(
                    f"Set maintenance window for {flavor.name} {start} - {end}"
                )
            except Exception as e:
                print(f"Failed to set maintenance window for {flavor.name}")
                print(e)


def main():
    cmd = WarreMaintenance()
    cmd.run()


if __name__ == '__main__':
    main()
