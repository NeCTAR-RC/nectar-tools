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

    def get_flavors_from_warre_id(self, flavors, warre_id):
        warre_id_regex = re.escape(warre_id)
        warre_id_flavors = []
        for flavor in flavors:
            if flavor.active:
                try:
                    if re.search(warre_id_regex, flavor.properties):
                        warre_id_flavors.append(flavor)
                except Exception:
                    pass
        return warre_id_flavors

    def add_hosts_flavors_to_table(self, hosts, flavors, table):
        for host in hosts:
            flavor_names = []
            warre_id = self.get_host_warre_id(host)
            if warre_id:
                warre_id_flavors = self.get_flavors_from_warre_id(
                    flavors, warre_id
                )
                for flavor in warre_id_flavors:
                    try:
                        flavor_name = flavor.name
                        flavor_names.append(flavor_name)
                    except Exception:
                        flavor_name = None
                    try:
                        host_name = host['hypervisor_hostname']
                    except Exception:
                        host_name = None
                    table.add_row([host_name, warre_id, flavor_names])
        return table


def main():
    WarreHostFlavors().run()


if __name__ == '__main__':
    main()
