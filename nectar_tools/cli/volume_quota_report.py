#!/usr/bin/env python3

import argparse
import os

from collections import defaultdict
from keystoneauth1.identity import v3
from keystoneauth1 import session
from nectarallocationclient import client


def get_keystone_auth():
    """
    Construct keystone auth using standard OS_ environment variables,
    supporting both token (OS_TOKEN) and password authentication.
    """
    auth_url = os.environ.get('OS_AUTH_URL')
    if not auth_url:
        raise ValueError(
            "Environment variable OS_AUTH_URL is missing. Please source your openrc file."
        )

    token = os.environ.get('OS_TOKEN')

    if token:
        return v3.Token(
            auth_url=auth_url,
            token=token,
            project_id=os.environ.get('OS_PROJECT_ID'),
        )
    else:
        return v3.Password(
            auth_url=auth_url,
            username=os.environ.get('OS_USERNAME'),
            password=os.environ.get('OS_PASSWORD'),
            project_name=os.environ.get('OS_PROJECT_NAME'),
            project_domain_name=os.environ.get(
                'OS_PROJECT_DOMAIN_NAME', 'Default'
            ),
            user_domain_name=os.environ.get('OS_USER_DOMAIN_NAME', 'Default'),
        )


def get_attr(obj, attr_name, default=None):
    """Helper to safely fetch attributes whether the API returns a dict or an object."""
    if isinstance(obj, dict):
        return obj.get(attr_name, default)
    return getattr(obj, attr_name, default)


def main():
    parser = argparse.ArgumentParser(
        description="Calculate OpenStack volume quotas dynamically per site."
    )
    parser.add_argument(
        '--site',
        type=str,
        action='append',
        dest='sites',
        default=None,
        metavar='SITE',
        help="Filter to a specific site/zone (case-insensitive). May be specified multiple times.",
    )
    parser.add_argument(
        '--output-format',
        choices=['table', 'json'],
        default='table',
        help="Output format: 'table' (default) or 'json'.",
    )
    args = parser.parse_args()

    site_filter = {s.lower() for s in args.sites} if args.sites else None

    # Authenticate and initialize Nectar Allocation Client
    try:
        auth = get_keystone_auth()
    except ValueError as e:
        print(f"Authentication Error: {e}")
        return

    sess = session.Session(auth=auth)
    allocation_client = client.Client('1', session=sess)

    # Track national and non-national totals per site
    site_national = defaultdict(int)
    site_non_national = defaultdict(int)

    if args.output_format == 'table':
        print(
            f"Fetching approved allocations (Site filter: {', '.join(sorted(args.sites)) if args.sites else 'all'})..."
        )

    # Filter for Approved ('A') allocations to get the current allocated totals
    allocations = allocation_client.allocations.list(
        parent_request__isnull=True, status='A'
    )

    for alloc in allocations:
        is_national = get_attr(alloc, 'national', False)

        # Get quotas tied to the allocation
        quotas = get_attr(alloc, 'quotas', [])
        if not quotas and hasattr(allocation_client, 'quotas'):
            try:
                quotas = allocation_client.quotas.list(
                    allocation=get_attr(alloc, 'id')
                )
            except Exception:
                pass

        for q in quotas:
            resource = get_attr(q, 'resource')
            if not resource or resource != 'volume.gigabytes':
                continue

            site = get_attr(q, 'zone')
            if not site:
                continue

            # Apply site filter if specified
            if site_filter and site.lower() not in site_filter:
                continue

            try:
                quota_value = int(get_attr(q, 'quota', 0))
            except ValueError:
                quota_value = 0

            if is_national:
                site_national[site] += quota_value
            else:
                site_non_national[site] += quota_value

    # Collect all sites seen across both buckets and group related sites together.
    # A "base" site is one whose name appears as a suffix in another site name
    # (e.g. "melbourne" is the base of "encrypted-melbourne", "performance-melbourne").
    # Ordering: base site first (alphabetically across bases), then its variants
    # sorted alphabetically, then any site that has no recognised base on its own.
    raw_sites = set(site_national) | set(site_non_national)

    def site_sort_key(site):
        # Find the longest other site name that this site ends with (its base).
        # If the site itself is a base (or standalone), use the site name as the base.
        base = next(
            (
                other
                for other in sorted(raw_sites, key=len, reverse=True)
                if other != site and site.endswith(other)
            ),
            site,  # fallback: site is its own base
        )
        # Primary sort: base name; secondary: empty string so the bare base
        # sorts before its prefixed variants, then alphabetical among variants.
        is_variant = base != site
        return (base, is_variant, site)

    all_sites = sorted(raw_sites, key=site_sort_key)

    # Build per-site results in display order
    grand_national = sum(site_national.values())
    grand_non_national = sum(site_non_national.values())
    grand_total = grand_national + grand_non_national

    if args.output_format == 'json':
        import json

        output = {
            "sites": [
                {
                    "site": site,
                    "national_gb": site_national.get(site, 0),
                    "non_national_gb": site_non_national.get(site, 0),
                    "total_gb": site_national.get(site, 0)
                    + site_non_national.get(site, 0),
                }
                for site in all_sites
            ],
            "totals": {
                "national_gb": grand_national,
                "non_national_gb": grand_non_national,
                "total_gb": grand_total,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        # Default: human-readable table
        print("\n--- Volume Quota Totals per Site ---")
        if not all_sites:
            print(
                "No site-specific volume quotas found matching the given criteria."
            )
        else:
            col_site = max((len(s) for s in all_sites), default=15)
            col_site = max(col_site, 15)
            header = f"{'Site':<{col_site}}  {'National':>12}  {'Non-National':>12}  {'Total':>12}"
            separator = "-" * len(header)
            print(header)
            print(separator)
            for site in all_sites:
                national = site_national.get(site, 0)
                non_national = site_non_national.get(site, 0)
                total = national + non_national
                print(
                    f"{site:<{col_site}}  {national:>9} GB  {non_national:>9} GB  {total:>9} GB"
                )

            # Grand totals row
            print(separator)
            print(
                f"{'TOTAL':<{col_site}}  {grand_national:>9} GB  {grand_non_national:>9} GB  {grand_total:>9} GB"
            )


if __name__ == '__main__':
    main()
