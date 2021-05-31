#!/usr/bin/env python3

import os
import argparse
import sys
import time
import datetime

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy import MetaData
from sqlalchemy import select

from gnocchiclient import client as gnocchiclient
from keystoneauth1 import loading
from keystoneauth1 import session



TEMPEST_PROJECT_IDS = [
    '0070581e858f4a88b60fbaf78a1e3370',
    '0aafa975a7ca49419e1b902af8da1203',
    '176f0768bd22470e9b3e7301b462261d',
    '269339d23ce24859bba93d0523e89ebb',
    '272293d28f974f17a9b4604254f429e1',
    '5e743ae0b1304dbe8b3f4da03edfced6',
    '65834c7b361640e992af46556e6d3ac4',
    '71787075c1334ed3b6e768c2d5ffc2bf',
    'de6188d84eda47828c2c46832435a249',
    '67071c396d0144e6946db781cf433269',
    '6f522aefdc6042c39f251df6fe762a4b',
    'b4296d08a2bd4af9bb26bbe8862f8c3a',
    '79698522e8eb45039ed838e7ff8dcd74',
    '869c23e1547443599f1f348a6670548d',
    '88241d64b1ff472c9b45ea7f9670e04f',
    'b75869fa21614196a44eb9f94535ea55',
    'cda2b84c1fe949c5b9c664ef101be06a',
    'e183df4e2bd045f7a9cbdb37a99929a']


MAX_TIME_DIFF = 3600


def get_session():
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=os.environ.get('OS_AUTH_URL'),
                                    username=os.environ.get('OS_USERNAME'),
                                    password=os.environ.get('OS_PASSWORD'),
                                    project_name=os.environ.get('OS_PROJECT_NAME'),
                                    user_domain_id='default',
                                    project_domain_id='default')
    return session.Session(auth=auth)


def get_gnocchi_client(sess=None):
    if not sess:
        sess = get_session()
    return gnocchiclient.Client('1', session=sess)


def sync_cell(uri, cell, changes_since):
    if cell == 'cell0':
        print("Skipping cell0")
        return
    print("-------------------------------")
    print("Syncing Cell %s" % cell)
    
    g_client = get_gnocchi_client()
    
    engine = create_engine(uri, connect_args={'connect_timeout': 5})
    with engine.connect() as conn:
        meta = MetaData(engine)
        meta.reflect()

        instance_t = meta.tables['instances']
        query = select([instance_t.c.uuid, instance_t.c.created_at, instance_t.c.deleted_at, instance_t.c.project_id, instance_t.c.vm_state]).where(sqlalchemy.and_(~instance_t.c.project_id.in_(TEMPEST_PROJECT_IDS), instance_t.c.updated_at > changes_since))
        instances = conn.execute(query).fetchall()

    total = len(instances)
    processed = 0
    for i in instances:
        if processed%1000 == 0:
            print("Processed %s/%s" % (processed, total))
        processed += 1
        id, start, end, project_id, state = i
        if state in ['error', 'building']:
            continue
        if end:
            duration = (end - start)
        else:
            duration = 'ongoing'
        if id == '00000000-0000-0000-0000-000000000000':
            continue
        if project_id in TEMPEST_PROJECT_IDS:
            continue
        #start = datetime.datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
        
    
        #id = '32dc14a4-1b3b-4e8f-b605-69447bb98dbe'
        #print(end)
        try:
            gnocchi_instance = g_client.resource.get('generic', id)
        except Exception:
            if not end:
                print("Running instance not in gnocchi %s duration: %s" % (id, duration))
            elif (end - start).total_seconds() > MAX_TIME_DIFF:
                print("No instance in gnocchi %s - project: %s duration: %s" % (id, project_id, duration))
        else:
            updates = {}
            g_start = gnocchi_instance.get('started_at').split('+')[0]
            try:
                g_start = datetime.datetime.strptime(g_start, '%Y-%m-%dT%H:%M:%S.%f')
            except ValueError:
                g_start = datetime.datetime.strptime(g_start, '%Y-%m-%dT%H:%M:%S')
            g_end = gnocchi_instance.get('ended_at')
            if g_end is not None:
                g_end = g_end.split('+')[0]
                try:
                    g_end = datetime.datetime.strptime(g_end, '%Y-%m-%dT%H:%M:%S.%f')
                except ValueError:
                    g_end = datetime.datetime.strptime(g_end, '%Y-%m-%dT%H:%M:%S')
            if (g_start - start).total_seconds() > MAX_TIME_DIFF:
                updates['started_at'] = str(start)
                print()                    
                print("g started %s" % g_start)
                print("n started %s" % start)
            if end and not g_end:
                print("Deleted instance not set in gnocchi")
                updates['ended_at'] = str(end)
            elif g_end and not end:
                print("Non deleted instance deleted in gnocchi!!!!!! %s" % id)
            elif g_end and (g_end - end).total_seconds() > MAX_TIME_DIFF:
                print()
                print("g ended %s" % g_end)
                print("n ended %s" % end)
                updates['ended_at'] = str(end)

            if updates:
                print("Updating %s with %s" % (id, updates))
                try:
                    # Need to set start before end in case current start is > correct end
                    if updates.get('started_at'):
                        g_client.resource.update(
                            'generic', id,
                            {'started_at': updates['started_at']})
                    if updates.get('ended_at'):
                        g_client.resource.update(
                            'generic', id,
                            {'ended_at': updates['ended_at']})
                except Exception as e:
                    print("Failed updating %s" % id)
                    print(e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Check cell database connectivity.')

    parser.add_argument('--name', action='store',
                        required=False, type=str,
                        help='Nova cell name')

    parser.add_argument('--nova-db-uri',
                        action='store',
                        required=True, type=str,
                        help='Nova Api database uri')
    parser.add_argument('--changes-since',
                        action='store',
                        required=True, type=str,
                        help='Query nova DBs for instances changes since. YYYY-MM-DD')
    arguments = parser.parse_args()

    engine = create_engine(arguments.nova_db_uri,
                           connect_args={'connect_timeout': 5})

    cell_connections = []
    name = arguments.name
    try:
        with engine.connect() as conn:
            meta = MetaData(engine)
            meta.reflect()
            cell_mappings = meta.tables['cell_mappings']

            query = select([cell_mappings.c.database_connection,
                            cell_mappings.c.name])
            if name:
                query = query.where(
                    cell_mappings.c.name == arguments.name)
            cell_connections = conn.execute(query).fetchall()
    except Exception as e:
        print("Error - nova api database is not reachable")
        print(e)

    if len(cell_connections) > 0:
        for cell in cell_connections:
            sync_cell(*(cell), changes_since=arguments.changes_since)
