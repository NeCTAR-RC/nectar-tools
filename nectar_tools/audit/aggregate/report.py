"""Render the aggregate routing audit as HTML and/or Markdown.

Pure rendering helpers: no OpenStack access. The caller passes a gathered
graph model, the subject -> aggregate routing edges, and the collected
conflicts; these are handed to Jinja2 templates under templates/audit/.
"""

import os
import re

import jinja2


TEMPLATE_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'templates', 'audit')
)


def _aggregate_rows(graph):
    """Flatten aggregates into template-friendly dicts."""
    from nectar_tools.audit.aggregate import aggregate as agg

    rows = []
    for aggr in graph['aggregates']:
        properties = {
            k: v
            for k, v in (aggr.metadata or {}).items()
            if k not in agg.RESERVED_KEYS
        }
        rows.append(
            {
                'name': aggr.name,
                'availability_zone': aggr.availability_zone,
                'hosts': sorted(aggr.hosts or []),
                'properties': properties,
            }
        )
    return rows


KIND_COLOUR = {
    'flavor': '#2A7B9B',
    'image': '#7B6DAA',
    'project': '#D4A843',
}


def _svg_layout(edges):
    """Compute a simple two-column node/edge layout for the relation chart.

    Subjects (flavors/images/projects) are placed in the left column and
    aggregates in the right column, with edges drawn between them. Returns a
    dict with node and edge geometry consumed by the HTML template.
    """
    subjects = []
    seen_subjects = set()
    aggregates = []
    seen_aggs = set()
    for e in edges:
        skey = (e['kind'], e['subject'])
        if skey not in seen_subjects:
            seen_subjects.add(skey)
            subjects.append(skey)
        if e['aggregate'] not in seen_aggs:
            seen_aggs.add(e['aggregate'])
            aggregates.append(e['aggregate'])

    row_h = 46
    pad = 30
    rows = max(len(subjects), len(aggregates), 1)
    height = pad * 2 + row_h * rows
    left_x, right_x = 40, 560

    subj_pos = {}
    subj_nodes = []
    for i, (kind, name) in enumerate(subjects):
        y = pad + row_h * i + row_h / 2
        subj_pos[(kind, name)] = y
        subj_nodes.append(
            {
                'kind': kind,
                'name': name,
                'x': left_x,
                'y': y,
                'colour': KIND_COLOUR.get(kind, '#6B6560'),
            }
        )

    agg_pos = {}
    agg_nodes = []
    for i, name in enumerate(aggregates):
        y = pad + row_h * i + row_h / 2
        agg_pos[name] = y
        agg_nodes.append({'name': name, 'x': right_x, 'y': y})

    edge_lines = []
    for e in edges:
        y1 = subj_pos[(e['kind'], e['subject'])]
        y2 = agg_pos[e['aggregate']]
        edge_lines.append(
            {
                'x1': left_x + 180,
                'y1': y1,
                'x2': right_x,
                'y2': y2,
                'via': e['via'],
                'colour': KIND_COLOUR.get(e['kind'], '#6B6560'),
            }
        )

    return {
        'width': 760,
        'height': height,
        'subjects': subj_nodes,
        'aggregates': agg_nodes,
        'edges': edge_lines,
    }


def _mermaid_id(prefix, name):
    safe = re.sub(r'[^0-9A-Za-z_]', '_', str(name))
    return f"{prefix}_{safe}"


def _mermaid_edges(edges):
    """Edges with Mermaid-safe node ids/labels for the Markdown diagram."""
    out = []
    for e in edges:
        out.append(
            {
                'src_id': _mermaid_id(e['kind'], e['subject']),
                'src_label': f"{e['kind']}: {e['subject']}",
                'dst_id': _mermaid_id('agg', e['aggregate']),
                'dst_label': e['aggregate'],
                'via': e['via'],
            }
        )
    return out


def _context(graph, edges, conflicts):
    return {
        'az': graph['az'],
        'aggregates': _aggregate_rows(graph),
        'edges': edges,
        'svg': _svg_layout(edges),
        'mermaid_edges': _mermaid_edges(edges),
        'conflicts': conflicts,
        'flavor_count': len(graph['flavors']),
        'image_count': len(graph['images']),
        'host_count': len(graph['az_hosts']),
    }


def _render(template_name, context):
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=jinja2.select_autoescape(['html']),
    )
    return env.get_template(template_name).render(context)


def render(graph, edges, conflicts, output_path, fmt='html'):
    """Write the report. Returns the list of file paths written."""
    context = _context(graph, edges, conflicts)
    base, ext = os.path.splitext(output_path)

    formats = ['html', 'md'] if fmt == 'both' else [fmt]
    written = []
    for f in formats:
        template = 'aggregate.html' if f == 'html' else 'aggregate.md'
        if fmt == 'both' or not ext:
            path = f"{base}.{f}"
        else:
            path = output_path
        content = _render(template, context)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        written.append(path)
    return written
