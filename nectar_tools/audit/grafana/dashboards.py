def running_instances_dashboard(project, id=None, uid=None):
    dashboard = {
        "description": "Lists running instances",
        "editable": True,
        "id": id,
        "panels": [
            {
                "aliasColors": {},
                "bars": False,
                "dashLength": 10,
                "dashes": False,
                "datasource": "Gnocchi",
                "fill": 1,
                "gridPos": {
                    "h": 7,
                    "w": 12,
                    "x": 0,
                    "y": 0
                },
                "id": 1,
                "legend": {
                    "avg": False,
                    "current": False,
                    "max": False,
                    "min": False,
                    "show": True,
                    "total": False,
                    "values": False
                },
                "lines": True,
                "linewidth": 1,
                "links": [],
                "NonePointMode": "None",
                "paceLength": 10,
                "percentage": False,
                "pointradius": 5,
                "points": False,
                "renderer": "flot",
                "seriesOverrides": [],
                "spaceLength": 10,
                "stack": False,
                "steppedLine": False,
                "targets": [
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "label": "${metric}",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(clip (metric cpu_util mean) 100)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "A",
                        "resource_id": "$instance_id",
                        "resource_search": "id=$instance_id",
                        "resource_type": "instance"
                    }
                ],
                "thresholds": [],
                "timeFrom": None,
                "timeRegions": [],
                "timeShift": None,
                "title": "CPU utilisation",
                "tooltip": {
                    "shared": True,
                    "sort": 0,
                    "value_type": "individual"
                },
                "type": "graph",
                "xaxis": {
                    "buckets": None,
                    "mode": "time",
                    "name": None,
                    "show": True,
                    "values": []
                },
                "yaxes": [
                    {
                        "format": "percent",
                        "label": "",
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    },
                    {
                        "format": "short",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    }
                ],
                "yaxis": {
                    "align": False,
                    "alignLevel": None
                }
            },
            {
                "aliasColors": {},
                "bars": False,
                "dashLength": 10,
                "dashes": False,
                "datasource": "Gnocchi",
                "fill": 1,
                "gridPos": {
                    "h": 7,
                    "w": 12,
                    "x": 12,
                    "y": 0
                },
                "id": 3,
                "legend": {
                    "avg": False,
                    "current": False,
                    "max": False,
                    "min": False,
                    "show": True,
                    "total": False,
                    "values": False
                },
                "lines": True,
                "linewidth": 1,
                "links": [],
                "NonePointMode": "None",
                "paceLength": 10,
                "percentage": False,
                "pointradius": 5,
                "points": False,
                "renderer": "flot",
                "seriesOverrides": [],
                "spaceLength": 10,
                "stack": False,
                "steppedLine": False,
                "targets": [
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "label": "${metric}",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric memory.usage mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "A",
                        "resource_id": "$instance_id",
                        "resource_search": "id=$instance_id",
                        "resource_type": "instance"
                    },
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "label": "${metric}",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric memory mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "B",
                        "resource_id": "$instance_id",
                        "resource_search": "id=$instance_id",
                        "resource_type": "instance"
                    }
                ],
                "thresholds": [],
                "timeFrom": None,
                "timeRegions": [],
                "timeShift": None,
                "title": "Memory",
                "tooltip": {
                    "shared": True,
                    "sort": 0,
                    "value_type": "individual"
                },
                "type": "graph",
                "xaxis": {
                    "buckets": None,
                    "mode": "time",
                    "name": None,
                    "show": True,
                    "values": []
                },
                "yaxes": [
                    {
                        "format": "decmbytes",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    },
                    {
                        "format": "short",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    }
                ],
                "yaxis": {
                    "align": False,
                    "alignLevel": None
                }
            },
            {
                "aliasColors": {},
                "bars": False,
                "dashLength": 10,
                "dashes": False,
                "datasource": "Gnocchi",
                "fill": 1,
                "gridPos": {
                    "h": 7,
                    "w": 12,
                    "x": 0,
                    "y": 7
                },
                "id": 2,
                "legend": {
                    "avg": False,
                    "current": False,
                    "max": False,
                    "min": False,
                    "show": True,
                    "total": False,
                    "values": False
                },
                "lines": True,
                "linewidth": 1,
                "links": [],
                "NonePointMode": "None",
                "paceLength": 10,
                "percentage": False,
                "pointradius": 5,
                "points": False,
                "renderer": "flot",
                "seriesOverrides": [],
                "spaceLength": 10,
                "stack": False,
                "steppedLine": False,
                "targets": [
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "label": "${name}-usage",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric disk.device.usage mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "A",
                        "resource_id": "$instance_id",
                        "resource_search": "instance_id=$instance_id",
                        "resource_type": "instance_disk"
                    },
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "hide": False,
                        "label": "${name}-capacity",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric disk.device.capacity mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "B",
                        "resource_id": "$instance_id",
                        "resource_search": "instance_id=$instance_id",
                        "resource_type": "instance_disk"
                    }
                ],
                "thresholds": [],
                "timeFrom": None,
                "timeRegions": [],
                "timeShift": None,
                "title": "Disk usage",
                "tooltip": {
                    "shared": True,
                    "sort": 0,
                    "value_type": "individual"
                },
                "type": "graph",
                "xaxis": {
                    "buckets": None,
                    "mode": "time",
                    "name": None,
                    "show": True,
                    "values": []
                },
                "yaxes": [
                    {
                        "format": "decbytes",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    },
                    {
                        "format": "short",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    }
                ],
                "yaxis": {
                    "align": False,
                    "alignLevel": None
                }
        },
            {
                "aliasColors": {},
                "bars": False,
                "dashLength": 10,
                "dashes": False,
                "datasource": "Gnocchi",
                "fill": 0,
                "gridPos": {
                    "h": 7,
                    "w": 12,
                    "x": 12,
                    "y": 7
                },
                "id": 5,
                "legend": {
                    "avg": False,
                    "current": False,
                    "max": False,
                    "min": False,
                    "show": True,
                    "total": False,
                    "values": False
                },
                "lines": True,
                "linewidth": 1,
                "links": [],
                "NonePointMode": "None",
                "paceLength": 10,
                "percentage": False,
                "pointradius": 5,
                "points": False,
                "renderer": "flot",
                "seriesOverrides": [],
                "spaceLength": 10,
                "stack": False,
                "steppedLine": False,
                "targets": [
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "label": "${name}-read",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric disk.device.read.bytes.rate mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "A",
                        "resource_id": "$instance_id",
                        "resource_search": "instance_id=$instance_id",
                        "resource_type": "instance_disk"
                    },
                    {
                    "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "hide": False,
                        "label": "${name}-write",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric disk.device.write.bytes.rate mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "B",
                        "resource_id": "$instance_id",
                        "resource_search": "instance_id=$instance_id",
                        "resource_type": "instance_disk"
                    }
            ],
                "thresholds": [],
                "timeFrom": None,
                "timeRegions": [],
                "timeShift": None,
                "title": "Disk read/write",
                "tooltip": {
                    "shared": True,
                    "sort": 0,
                    "value_type": "individual"
                },
                "type": "graph",
                "xaxis": {
                    "buckets": None,
                    "mode": "time",
                    "name": None,
                    "show": True,
                    "values": []
                },
                "yaxes": [
                    {
                        "format": "Bps",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    },
                    {
                        "format": "short",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    }
                ],
                "yaxis": {
                    "align": False,
                    "alignLevel": None
                }
            },
            {
                "aliasColors": {},
                "bars": False,
                "dashLength": 10,
                "dashes": False,
                "datasource": "Gnocchi",
                "fill": 0,
                "gridPos": {
                    "h": 7,
                    "w": 12,
                    "x": 0,
                    "y": 14
                },
                "id": 4,
                "legend": {
                    "avg": False,
                    "current": False,
                    "max": False,
                    "min": False,
                    "show": True,
                    "total": False,
                    "values": False
                },
                "lines": True,
                "linewidth": 1,
                "links": [],
                "NonePointMode": "None",
                "paceLength": 10,
                "percentage": False,
                "pointradius": 5,
                "points": False,
                "renderer": "flot",
                "seriesOverrides": [],
                "spaceLength": 10,
                "stack": False,
                "steppedLine": False,
                "targets": [
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "label": "${name}-incoming",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric network.incoming.bytes.rate mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "A",
                        "resource_id": "$instance_id",
                        "resource_search": "instance_id=$instance_id and ended_at = none",
                        "resource_type": "instance_network_interface"
                    },
                    {
                        "aggregator": "none found",
                        "draw_missing_datapoint_as_zero": True,
                        "fill": 0,
                        "granularity": "",
                        "groupby": "",
                        "hide": False,
                        "label": "${name}-outgoing",
                        "metric_name": "none found",
                        "needed_overlap": 0,
                        "operations": "(metric network.outgoing.bytes.rate mean)",
                        "queryMode": "dynamic_aggregates",
                        "reaggregator": "none",
                        "refId": "B",
                        "resource_id": "$instance_id",
                        "resource_search": "instance_id=$instance_id and ended_at = none",
                        "resource_type": "instance_network_interface"
                    }
                ],
                "thresholds": [],
                "timeFrom": None,
                "timeRegions": [],
                "timeShift": None,
                "title": "Network",
                "tooltip": {
                    "shared": True,
                    "sort": 0,
                    "value_type": "individual"
                },
                "type": "graph",
                "xaxis": {
                    "buckets": None,
                    "mode": "time",
                    "name": None,
                    "show": True,
                    "values": []
                },
                "yaxes": [
                    {
                        "format": "Bps",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    },
                    {
                        "format": "short",
                        "label": None,
                        "logBase": 1,
                        "max": None,
                        "min": None,
                        "show": True
                    }
                ],
                "yaxis": {
                    "align": False,
                    "alignLevel": None
                }
            }
        ],
        "templating": {
            "list": [
                {
                    "allValue": None,
                    "datasource": "Gnocchi",
                    "definition": "resources(instance, $display_name, original_resource_id,project_id = \"%s\" and ended_at = none) " % project.id,
                    "hide": 0,
                    "includeAll": False,
                    "label": "Name",
                    "multi": False,
                    "name": "instance_id",
                    "options": [],
                    "query": "resources(instance, $display_name, original_resource_id,project_id = \"%s\" and ended_at = none) " % project.id,
                    "refresh": 1,
                    "regex": "",
                    "skipUrlSync": False,
                    "sort": 0,
                    "tagValuesQuery": "",
                    "tags": [],
                    "tagsQuery": "",
                    "type": "query",
                    "useTags": False
                }
            ]
        },
        "time": {
            "from": "now-7d",
            "to": "now"
        },
        "timepicker": {
            "refresh_intervals": [
                "5s",
                "10s",
                "30s",
                "1m",
                "5m",
                "15m",
                "30m",
                "1h",
                "2h",
                "1d"
            ],
            "time_options": [
                "5m",
                "15m",
                "1h",
                "6h",
                "12h",
                "24h",
                "2d",
                "7d",
                "30d"
            ]
        },
        "title": "Running Instances - %s" % project.name,
        "uid": uid,
    }
    return dashboard
