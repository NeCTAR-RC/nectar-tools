# Aggregate routing audit — {{ az }}

{{ aggregates|length }} aggregate(s) · {{ host_count }} host(s) · {{ flavor_count }} flavor(s) · {{ image_count }} image(s) scanned.

## Routing relation chart

{% if mermaid_edges %}
```mermaid
graph LR
{%- for e in mermaid_edges %}
  {{ e.src_id }}["{{ e.src_label }}"] -->|{{ e.via }}| {{ e.dst_id }}(["{{ e.dst_label }}"])
{%- endfor %}
```
{% else %}
_No routing edges found: no flavor, image, or project metadata references the aggregates in this zone._
{% endif %}

## Aggregates

| Aggregate | AZ | Hosts | Properties |
|-----------|----|-------|------------|
{% for a in aggregates -%}
| {{ a.name }} | {{ a.availability_zone or '—' }} | {{ a.hosts|length }} | {% for k, v in a.properties.items() %}`{{ k }}={{ v }}` {% else %}—{% endfor %} |
{% endfor %}

## Conflicts

### Hosts in Placement but in no aggregate ({{ conflicts.hosts_without_aggregate|length }})

{% if conflicts.hosts_without_aggregate %}
{% for f in conflicts.hosts_without_aggregate %}- {{ f }}
{% endfor %}
{% else %}_No issues found._
{% endif %}

### Orphaned aggregate properties ({{ conflicts.orphaned_properties|length }})

{% if conflicts.orphaned_properties %}
{% for f in conflicts.orphaned_properties %}- {{ f }}
{% endfor %}
{% else %}_No issues found._
{% endif %}

### Metadata syntax errors ({{ conflicts.metadata_syntax|length }})

{% if conflicts.metadata_syntax %}
{% for f in conflicts.metadata_syntax %}- {{ f }}
{% endfor %}
{% else %}_No issues found._
{% endif %}
