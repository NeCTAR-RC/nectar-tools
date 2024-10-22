#!/usr/bin/env python
import argparse
import math

from nectar_tools import auth
from prettytable import PrettyTable


def get_host_list(agg_name, zone, aggrlist):
    hosts = set()
    hosts.update(
        get_hosts_from_aggregates(
            agg_name=agg_name, zone=zone, aggrlist=aggrlist
        )
    )
    return hosts


def get_aggregate_list():
    n_client = auth.get_nova_client()
    return n_client.aggregates.list()


def get_hosts_from_aggregates(agg_name=None, zone=None, aggrlist=None):
    all_hosts = set()
    zone_hosts = set()
    agg_name_hosts = set()
    for aggr in aggrlist:
        all_hosts.update(aggr.hosts)
        if aggr.availability_zone == zone:
            zone_hosts.update(aggr.hosts)
        if aggr.name == agg_name:
            agg_name_hosts.update(aggr.hosts)
    if agg_name and zone:
        return set.intersection(agg_name_hosts, zone_hosts)
    elif agg_name:
        return agg_name_hosts
    elif zone:
        return zone_hosts
    return all_hosts


def get_total_usable_inventory(inventory):
    total = inventory["total"]
    alloc_ratio = inventory["allocation_ratio"]
    reserved = inventory["reserved"]
    return (total - reserved) * alloc_ratio


def get_hosts_inventory_usage(hosts):
    hosts_inventory_usage = []
    p_client = auth.get_placement_client()
    rps = p_client.resource_providers.list()
    for host in hosts:
        for rp in rps:
            if rp.name.split(".")[0] == host.split(".")[0]:
                try:
                    total_usable_vcpu = math.floor(
                        get_total_usable_inventory(rp.inventories().VCPU)
                    )
                except AttributeError:
                    total_usable_vcpu = 0
                try:
                    total_usable_pcpu = math.floor(
                        get_total_usable_inventory(rp.inventories().PCPU)
                    )
                except AttributeError:
                    total_usable_pcpu = 0
                try:
                    total_usable_memory_gb = math.floor(
                        get_total_usable_inventory(rp.inventories().MEMORY_MB)
                        / 1024
                    )
                except AttributeError:
                    continue
                total_usable_disk_gb = math.floor(
                    get_total_usable_inventory(rp.inventories().DISK_GB)
                )
                try:
                    used_vcpu = rp.usages().VCPU
                    used_vcpu_percent = percentage(
                        used_vcpu, total_usable_vcpu
                    )
                except AttributeError:
                    used_vcpu = 0
                    used_vcpu_percent = 0
                try:
                    used_pcpu = rp.usages().PCPU
                    used_pcpu_percent = percentage(
                        used_pcpu, total_usable_pcpu
                    )
                except AttributeError:
                    used_pcpu = 0
                    used_pcpu_percent = 0
                used_memory_gb = math.floor((rp.usages().MEMORY_MB) / 1024)
                used_memory_gb_percent = percentage(
                    used_memory_gb, total_usable_memory_gb
                )
                used_disk_gb = rp.usages().DISK_GB
                used_disk_gb_percent = percentage(
                    used_disk_gb, total_usable_disk_gb
                )
                avail_vcpu = total_usable_vcpu - used_vcpu
                avail_pcpu = total_usable_pcpu - used_pcpu
                avail_memory_gb = total_usable_memory_gb - used_memory_gb
                avail_disk_gb = total_usable_disk_gb - used_disk_gb
                host_inventory_usage = {
                    "host": host,
                    "VCPU": total_usable_vcpu,
                    "USED_VCPU": used_vcpu,
                    "AVAIL_VCPU": avail_vcpu,
                    "USED_VCPU_%": used_vcpu_percent,
                    "PCPU": total_usable_pcpu,
                    "USED_PCPU": used_pcpu,
                    "AVAIL_PCPU": avail_pcpu,
                    "USED_PCPU_%": used_pcpu_percent,
                    "MEMORY_GB": total_usable_memory_gb,
                    "USED_MEMORY_GB": used_memory_gb,
                    "AVAIL_MEMORY_GB": avail_memory_gb,
                    "USED_MEMORY_GB_%": used_memory_gb_percent,
                    "DISK_GB": total_usable_disk_gb,
                    "USED_DISK_GB": used_disk_gb,
                    "AVAIL_DISK_GB": avail_disk_gb,
                    "USED_DISK_GB_%": used_disk_gb_percent,
                }
                hosts_inventory_usage.append(host_inventory_usage)
    return hosts_inventory_usage


def get_totals(hosts_inventory_usage):
    total_usable_vcpu = 0
    total_usable_pcpu = 0
    total_usable_memory_gb = 0
    total_usable_disk_gb = 0
    used_vcpu = 0
    used_pcpu = 0
    used_memory_gb = 0
    used_disk_gb = 0
    avail_vcpu = 0
    avail_pcpu = 0
    avail_memory_gb = 0
    avail_disk_gb = 0
    used_vcpu_percent = 0
    used_pcpu_percent = 0
    used_memory_gb_percent = 0
    used_disk_gb_percent = 0
    longest_hostname = ""
    for host in hosts_inventory_usage:
        if len(host["host"]) > len(longest_hostname):
            longest_hostname = host["host"]
        total_usable_vcpu += host["VCPU"]
        total_usable_pcpu += host["PCPU"]
        total_usable_memory_gb += host["MEMORY_GB"]
        total_usable_disk_gb += host["DISK_GB"]
        used_vcpu += host["USED_VCPU"]
        used_pcpu += host["USED_PCPU"]
        used_memory_gb += host["USED_MEMORY_GB"]
        used_disk_gb += host["USED_DISK_GB"]
        avail_vcpu += host["AVAIL_VCPU"]
        avail_pcpu += host["AVAIL_PCPU"]
        avail_memory_gb += host["AVAIL_MEMORY_GB"]
        avail_disk_gb += host["AVAIL_DISK_GB"]
    used_vcpu_percent = percentage(used_vcpu, total_usable_vcpu)
    used_pcpu_percent = percentage(used_pcpu, total_usable_pcpu)
    used_memory_gb_percent = percentage(used_memory_gb, total_usable_memory_gb)
    used_disk_gb_percent = percentage(used_disk_gb, total_usable_disk_gb)
    space = len(longest_hostname) * " "
    total_inventory_usage = {
        space: "TOTAL",
        "VCPU": total_usable_vcpu,
        "USED_VCPU": used_vcpu,
        "AVAIL_VCPU": avail_vcpu,
        "USED_VCPU_%": used_vcpu_percent,
        "PCPU": total_usable_pcpu,
        "USED_PCPU": used_pcpu,
        "AVAIL_PCPU": avail_pcpu,
        "USED_PCPU_%": used_pcpu_percent,
        "MEMORY_GB": total_usable_memory_gb,
        "USED_MEMORY_GB": used_memory_gb,
        "AVAIL_MEMORY_GB": avail_memory_gb,
        "USED_MEMORY_GB_%": used_memory_gb_percent,
        "DISK_GB": total_usable_disk_gb,
        "USED_DISK_GB": used_disk_gb,
        "AVAIL_DISK_GB": avail_disk_gb,
        "USED_DISK_GB_%": used_disk_gb_percent,
    }
    return total_inventory_usage


def percentage(part, whole):
    if whole == 0:
        return 0
    return math.floor(100 * float(part) / float(whole))


def print_table(
    hosts_inventory_usage,
    primary_sort_key=None,
    format='text',
    print_hosts=True,
    print_totals=True,
    reverse_sort=True,
):
    table = PrettyTable()
    for c in hosts_inventory_usage[0]:
        table.add_column(c, [])
    for host in hosts_inventory_usage:
        table.add_row([host.get(c, "") for c in hosts_inventory_usage[0]])
    table.sortby = primary_sort_key
    table.reversesort = reverse_sort

    total_inventory_usage = get_totals(hosts_inventory_usage)
    totals = PrettyTable()
    for c in total_inventory_usage:
        totals.add_column(c, [])
    totals.add_row([total_inventory_usage[c] for c in total_inventory_usage])
    if total_inventory_usage["PCPU"] == 0:
        for col in ["PCPU", "USED_PCPU", "AVAIL_PCPU", "USED_PCPU_%"]:
            table.del_column(col)
            totals.del_column(col)
    if print_hosts:
        print(table.get_formatted_string(format))
    if print_totals:
        print(totals.get_formatted_string(format))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--aggregate",
        type=str,
        help="name of aggregate to filter host list",
        default=None,
    )
    parser.add_argument(
        "-z",
        "--zone",
        type=str,
        help="availability zone to filter host list",
        default=None,
    )
    parser.add_argument(
        "--print_hosts",
        dest='print_hosts',
        help="print list of selected hosts (default)",
        action='store_true',
    )
    parser.add_argument(
        "--no_print_hosts",
        dest='print_hosts',
        help="do not print list of selected hosts",
        action='store_false',
    )
    parser.add_argument(
        "--print_totals",
        dest='print_totals',
        help="print totals (default)",
        action='store_true',
    )
    parser.add_argument(
        "--no_print_totals",
        dest='print_totals',
        help="do not print totals",
        action='store_false',
    )
    parser.add_argument(
        "--sort_key",
        type=str,
        help="key on which to sort table." "(default=AVAIL_MEMORY_GB)",
        choices=[
            'host',
            'VCPU',
            'USED_VCPU',
            'AVAIL_VCPU',
            'USED_VCPU_%',
            'PCPU',
            'USED_PCPU',
            'AVAIL_PCPU',
            'USED_PCPU_%',
            'MEMORY_GB',
            'USED_MEMORY_GB',
            'AVAIL_MEMORY_GB',
            'USED_MEMORY_GB_%',
            'DISK_GB',
            'USED_DISK_GB',
            'AVAIL_DISK_GB',
            'USED_DISK_GB_%',
        ],
        default='AVAIL_MEMORY_GB',
    )
    parser.add_argument(
        "--format",
        type=str,
        help="output format",
        choices=['text', 'html', 'json', 'csv', 'latex'],
        default='text',
    )
    parser.add_argument(
        "--reverse_sort",
        dest='reverse_sort',
        help="reverse sort order (default)",
        action='store_true',
    )
    parser.add_argument(
        "--no_reverse_sort",
        dest='reverse_sort',
        help="do not reverse sort order",
        action='store_false',
    )
    parser.set_defaults(print_hosts=True)
    parser.set_defaults(print_totals=True)
    parser.set_defaults(reverse_sort=True)
    return parser.parse_args()


def main():
    args = parse_args()
    agg_name = args.aggregate
    zone = args.zone
    print_hosts = args.print_hosts
    print_totals = args.print_totals
    sort_key = args.sort_key
    reverse_sort = args.reverse_sort
    output_format = args.format
    aggrlist = get_aggregate_list()
    hosts = get_host_list(agg_name, zone, aggrlist)
    if output_format == 'text':
        print(f"Zone Filter: {zone}")
        print(f"Aggregate Filter: {agg_name}")
    if hosts:
        hosts_inventory_usage = get_hosts_inventory_usage(hosts)
        print_table(
            hosts_inventory_usage,
            primary_sort_key=sort_key,
            reverse_sort=reverse_sort,
            format=output_format,
            print_hosts=print_hosts,
            print_totals=print_totals,
        )
    else:
        print("No hosts found.")


if __name__ == '__main__':
    main()
