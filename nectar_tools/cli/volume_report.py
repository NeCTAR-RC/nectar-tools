#!/usr/bin/env python3
"""
volume_report.py

Query an OpenStack cloud for per-project volume usage, enriched with
NeCTAR allocation metadata (chief investigator email, national flag).

Auth is taken from the standard OS_* environment variables (or a clouds.yaml
entry set via OS_CLOUD).

Usage:
    python volume_report.py [--az <availability-zone>] [--format {table,csv,json}]
                                   [--summarise]

Requirements:
    pip install python-openstackclient python-nectarallocationclient keystoneauth1
"""

import argparse
import csv
import json
import sys

from collections import defaultdict

try:
    import openstack
except ImportError:
    sys.exit(
        "ERROR: 'openstack' package not found.  "
        "Install with:  pip install openstacksdk"
    )

try:
    from nectarallocationclient import client as alloc_client
except ImportError:
    sys.exit(
        "ERROR: 'nectarallocationclient' package not found.  "
        "Install with:  pip install python-nectarallocationclient"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_openstack_connection():
    """Return an openstacksdk Connection using OS_* env vars."""
    try:
        conn = openstack.connect()
        # Verify we can authenticate
        conn.authorize()
        return conn
    except Exception as exc:
        sys.exit(f"ERROR: Could not connect to OpenStack: {exc}")


def build_allocation_client(conn):
    """
    Build a nectarallocationclient Client using the real keystoneauth1 Session
    from openstacksdk.

    The key fix: nectarallocationclient's SessionClient extends
    keystoneauth1.adapter.Adapter and calls self.get_project_id() on the
    session object. This method only exists on a genuine
    keystoneauth1.session.Session.

    openstacksdk's conn.session is its own internal proxy object (not a ks
    Session) and does NOT have get_project_id() -- hence the error:
      'Session' object has no attribute 'get_project_id'

    The correct accessor is conn.config.get_session(), which returns the
    underlying keystoneauth1.session.Session that openstacksdk built from the
    OS_* environment variables.
    """
    try:
        ks_sess = conn.config.get_session()
        nectar = alloc_client.Client(1, session=ks_sess)
        return nectar
    except Exception as exc:
        sys.exit(f"ERROR: Could not build allocation client: {exc}")


def get_volumes(conn, availability_zone=None):
    """
    Return a dict keyed by project_id mapping to total volume size (GiB).

    Only 'available', 'in-use', and 'error' volumes are included (i.e. not
    deleted/deleting).
    """
    ACTIVE_STATUSES = {
        'available',
        'in-use',
        'error',
        'reserved',
        'attaching',
        'detaching',
        'maintenance',
    }

    project_volume_gb = defaultdict(int)

    search_filters = {'all_tenants': True}
    if availability_zone:
        search_filters['availability_zone'] = availability_zone

    try:
        volumes = conn.block_storage.volumes(**search_filters)
    except Exception as exc:
        sys.exit(f"ERROR: Could not list volumes: {exc}")

    for vol in volumes:
        if vol.status not in ACTIVE_STATUSES:
            continue
        project_id = vol.get('os-vol-tenant-attr:tenant_id') or vol.project_id
        if project_id:
            project_volume_gb[project_id] += vol.size or 0

    return project_volume_gb


def get_project_names(conn, project_ids):
    """Return a dict {project_id: project_name} for the given IDs."""
    names = {}
    for pid in project_ids:
        try:
            proj = conn.identity.get_project(pid)
            names[pid] = proj.name
        except Exception:
            names[pid] = '<unknown>'
    return names


# Candidate field names for the CI email, in preference order.
# The API has used different names across versions; we try all known variants
# and take the first non-empty value from the raw _info dict.  Using _info
# avoids the same deserialisation masking that affected 'national':
# getattr(alloc, 'chief_investigator_email', '') returns '' both when the
# attribute is genuinely empty *and* when the client library never mapped it
# from the JSON response, making the empty result ambiguous.
_CI_FIELDS = (
    'chief_investigator_email',  # common current name
    'contact_email',  # seen in some deployments
    'investigator_email',  # older field name
    'ci_email',  # abbreviated variant
)


def get_allocations(nectar_client):
    """
    Return a dict keyed by project_id with allocation metadata.
    We only care about approved (status=A) top-level allocations.
    """
    alloc_map = {}
    try:
        allocations = nectar_client.allocations.list(
            status='A',  # Approved
            parent_request__isnull='true',  # BUG FIX: must be lowercase string
            # 'true', not Python bool True.
            # The API backend is Django REST
            # Framework which serialises query
            # params as strings; bool True
            # becomes 'True' which DRF does not
            # recognise as a valid boolean,
            # silently ignoring the filter and
            # returning child/amendment records
            # that often lack 'national=True'.
        )
    except Exception as exc:
        print(f"WARNING: Could not list allocations: {exc}", file=sys.stderr)
        return alloc_map

    for alloc in allocations:
        project_id = getattr(alloc, 'project_id', None)
        if not project_id:
            continue

        info = alloc._info if hasattr(alloc, '_info') else {}

        # Search _info for the first matching CI email field with a value.
        chief_investigator = ''
        for field in _CI_FIELDS:
            value = info.get(field, '') or ''
            if value.strip():
                chief_investigator = value.strip()
                break

        # BUG FIX: use _info.get() rather than getattr() with a False default.
        # getattr(alloc, 'national', False) returns False both when the
        # attribute is genuinely False *and* when it is absent from the
        # response payload, masking True values that were never deserialised.
        national = bool(info.get('national', False))

        alloc_map[project_id] = {
            'chief_investigator': chief_investigator,
            'national': national,
            'allocation_id': info.get('id'),
            'allocation_name': info.get('project_name'),
        }

    return alloc_map


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

HEADERS = [
    'project_id',
    'project_name',
    'volume_gb',
    'chief_investigator',
    'national',
]


def build_summary(rows):
    """Return a dict with volume_gb totals split by national status."""
    national_gb = sum(r['volume_gb'] for r in rows if r['national'])
    non_national_gb = sum(r['volume_gb'] for r in rows if not r['national'])
    return {
        'national_volume_gb': national_gb,
        'non_national_volume_gb': non_national_gb,
        'total_volume_gb': national_gb + non_national_gb,
    }


def print_table(rows, summarise=False):
    if not rows:
        print("No results.")
        return

    col_widths = {h: len(h) for h in HEADERS}
    for row in rows:
        for h in HEADERS:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ''))))

    sep = '+' + '+'.join('-' * (col_widths[h] + 2) for h in HEADERS) + '+'
    header_line = (
        '|' + '|'.join(f" {h:<{col_widths[h]}} " for h in HEADERS) + '|'
    )

    print(sep)
    print(header_line)
    print(sep)
    for row in rows:
        line = (
            '|'
            + '|'.join(
                f" {str(row.get(h, '')):<{col_widths[h]}} " for h in HEADERS
            )
            + '|'
        )
        print(line)
    print(sep)
    print(f"\n{len(rows)} project(s) found.")

    if summarise:
        summary = build_summary(rows)
        print("\nVolume summary:")
        print(f"  national=True  : {summary['national_volume_gb']:>10,} GiB")
        print(
            f"  national=False : {summary['non_national_volume_gb']:>10,} GiB"
        )
        print(f"  Total          : {summary['total_volume_gb']:>10,} GiB")


def print_csv(rows, summarise=False):
    writer = csv.DictWriter(
        sys.stdout, fieldnames=HEADERS, extrasaction='ignore'
    )
    writer.writeheader()
    writer.writerows(rows)

    if summarise:
        summary = build_summary(rows)
        print()
        print("national,volume_gb")
        print(f"True,{summary['national_volume_gb']}")
        print(f"False,{summary['non_national_volume_gb']}")
        print(f"Total,{summary['total_volume_gb']}")


def print_json(rows, summarise=False):
    """
    Default output format.

    Without --summarise:
        A JSON array of per-project records.

    With --summarise:
        A JSON object with two keys:
          - "projects"  : the per-project array
          - "summary"   : national_volume_gb / non_national_volume_gb / total_volume_gb
    """
    if summarise:
        output = {
            'projects': rows,
            'summary': build_summary(rows),
        }
    else:
        output = rows

    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description='Report per-project volume usage with NeCTAR allocation info.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--az',
        '--availability-zone',
        dest='availability_zone',
        default=None,
        metavar='AZ',
        help='Filter volumes by availability zone (e.g. melbourne-qh2)',
    )
    parser.add_argument(
        '--format',
        choices=['table', 'csv', 'json'],
        default='json',
        help='Output format (default: json)',
    )
    parser.add_argument(
        '--national-only',
        action='store_true',
        help='Only show national=True allocations',
    )
    parser.add_argument(
        '--summarise',
        action='store_true',
        help=(
            'Append a volume summary broken down by national=True / national=False. '
            'For JSON output this adds a "summary" key alongside "projects"; '
            'for table/csv it appends extra rows.'
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    print("Connecting to OpenStack …", file=sys.stderr)
    conn = build_openstack_connection()

    print("Building NeCTAR allocation client …", file=sys.stderr)
    nectar = build_allocation_client(conn)

    az_label = args.availability_zone or '(all)'
    print(
        f"Fetching volumes for availability zone: {az_label} …",
        file=sys.stderr,
    )
    project_volumes = get_volumes(conn, args.availability_zone)

    if not project_volumes:
        print("No volumes found matching the criteria.", file=sys.stderr)
        sys.exit(0)

    print(
        f"Resolving {len(project_volumes)} project name(s) …", file=sys.stderr
    )
    project_names = get_project_names(conn, list(project_volumes.keys()))

    print("Fetching NeCTAR allocations …", file=sys.stderr)
    alloc_map = get_allocations(nectar)

    # Build result rows
    rows = []
    for project_id, volume_gb in sorted(
        project_volumes.items(), key=lambda x: -x[1]
    ):
        alloc_info = alloc_map.get(project_id, {})
        national = alloc_info.get('national', False)

        if args.national_only and not national:
            continue

        rows.append(
            {
                'project_id': project_id,
                'project_name': project_names.get(project_id, '<unknown>'),
                'volume_gb': volume_gb,
                'chief_investigator': alloc_info.get('chief_investigator', ''),
                'national': national,
            }
        )

    # Output
    formatters = {
        'table': print_table,
        'csv': print_csv,
        'json': print_json,
    }
    formatters[args.format](rows, summarise=args.summarise)


if __name__ == '__main__':
    main()
