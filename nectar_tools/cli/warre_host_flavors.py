import prettytable
import re

from nectar_tools import auth


class WarreHostFlavors:
    def run(self):
        w_client = auth.get_warre_client()
        b_client = auth.get_blazar_client()
        hosts = b_client.host.list()
        flavors = w_client.flavors.list(all_projects=True)
        pt = prettytable.PrettyTable(
            ['Blazar_Hostname', 'Warre_ID', 'Warre_Flavor_Name']
        )
        pt = self.add_hosts_flavors_to_table(hosts, flavors, pt)
        pt.sortby = "Blazar_Hostname"
        print(pt)

    def get_host_warre_id(self, host):
        try:
            return host['warre_id']
        except Exception:
            return None

    def get_flavor_from_warre_id(self, flavors, warre_id):
        warre_id_regex = re.escape(warre_id)
        for flavor in flavors:
            try:
                if re.search(warre_id_regex, flavor.properties):
                    return flavor
            except Exception:
                pass

    def add_hosts_flavors_to_table(self, hosts, flavors, table):
        for host in hosts:
            flavor_name = None
            warre_id = self.get_host_warre_id(host)
            if warre_id:
                flavor = self.get_flavor_from_warre_id(flavors, warre_id)
                try:
                    flavor_name = flavor.name
                except Exception:
                    flavor_name = None
                try:
                    host_name = host['hypervisor_hostname']
                except Exception:
                    host_name = None
                table.add_row([host_name, warre_id, flavor_name])
        return table


def main():
    WarreHostFlavors().run()


if __name__ == '__main__':
    main()
