#!/usr/bin/env python3

"""
Does an audit of glance and it's swift image store.
It will remove all swift objects that don't belong to
an active image in glance

You will need to run this with the same creds as what Glance API
uses.

"""
import argparse
from swiftclient import client as swiftclient

import glanceclient
from keystoneauth1 import loading
from keystoneauth1 import session
import os
import http


SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'


def get_session():
    username = os.environ.get('OS_USERNAME')
    password = os.environ.get('OS_PASSWORD')
    project_name = os.environ.get('OS_PROJECT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=auth_url,
                                    username=username,
                                    password=password,
                                    project_name=project_name,
                                    user_domain_id='default',
                                    project_domain_id='default')

    return session.Session(auth=auth)


def get_swift_client(sess=None, project_id=None):
    if not sess:
        sess = get_session()
    os_opts = {}
    if project_id:
        endpoint = sess.get_endpoint(service_type='object-store')
        auth_project = sess.get_project_id()
        endpoint = endpoint.replace('AUTH_%s' % auth_project,
                                    'AUTH_%s' % project_id)
        os_opts['object_storage_url'] = '%s' % endpoint
    return swiftclient.Connection(session=sess, os_options=os_opts)


def get_glance_client(sess=None, endpoint=None):
    if not sess:
        sess = get_session()
    return glanceclient.Client('2', session=sess, endpoint=endpoint)


def delete_swift_image(connection, container, obj, noop=True):
    size = 0.0
    try:
        # We request the manifest for the object. If one exists,
        # that means the object was uploaded in chunks/segments,
        # and we need to delete all the chunks as well as the
        # manifest.
        manifest = None
        try:
            headers = connection.head_object(container=container, obj=obj)
            size = float(headers.get('content-length'))
            manifest = headers.get('x-object-manifest')
        except swiftclient.ClientException as e:
            if e.http_status != http.client.NOT_FOUND:
                raise
        segment_error = False
        if manifest:
            # Delete all the chunks before the object manifest itself
            obj_container, obj_prefix = manifest.split('/', 1)
            segments = connection.get_container(
                obj_container, prefix=obj_prefix)[1]
            for segment in segments:
                try:
                    if not noop:
                        connection.delete_object(obj_container,
                                                 segment['name'])
                    print("Deleted %s/%s" % (obj_container, segment['name']))
                except swiftclient.ClientException:
                    msg = 'Unable to delete segment %(segment_name)s'
                    msg = msg % {'segment_name': segment['name']}
                    print(msg)
                    segment_error = True
        if not segment_error:
            # Only delete the manifest if no segment errors
            # Delete object (or, in segmented case, the manifest)
            if not noop:
                connection.delete_object(container, obj)
            print("Deleted %s/%s" % (container, obj))

    except swiftclient.ClientException as e:
        if e.http_status == http.client.NOT_FOUND:
            msg = "Swift could not find image at URI. %s/%s"
            print(msg % (container, obj))
            if not noop:
                shotgun_segments(connection, container, obj)
        else:
            print(e)
    return size


def shotgun_segments(connection, container, image_id):
    limit = 200
    segment = 1
    while segment < limit:
        obj = "%s-%05d" % (image_id, segment)
        try:
            connection.delete_object(container, obj)
            print("Deleted %s/%s" % (container, obj))
        except swiftclient.ClientException as e:
            if e.http_status == http.client.NOT_FOUND:
                pass
            else:
                print(e)
        segment += 1


def delete_image_set(gc, connection, image_set, container, noop=True):
    bytes_deleted = 0
    for image_id in image_set:
        delete = False
        try:
            try:
                image = gc.images.get(image_id)
            except Exception as e:
                print("Failed to get image with ID %s" % image_id)
                print(e)
                image = None
            if image is None:
                delete = True
            elif image.status == 'killed':
                delete = True
            else:
                delete = False
                #print("Skipping active image %s" % image_id)
                #print("Status: %s" % image.status)
                #print("Created: %s, Updated %s" % (image.created_at,
                #                                   image.updated_at))

        except glanceclient.exc.HTTPNotFound:
            delete = True
        if delete:
            size = delete_swift_image(connection, container,
                                      image_id, noop)
            bytes_deleted += size
    return bytes_deleted


def strip_segment(name):
    """Strips out segment part from image objects
    Eg. xxx-xxx-xxx-xxxxxx-00001
    or old style int image ids xxxx-00001
    """
    dashs = name.count('-')
    if dashs == 4 or dashs == 0:
        return name
    elif dashs == 1 or dashs == 5:
        return name.rsplit('-', 1)[0]
    else:
        raise Exception("Unknown object format %s" % name)


def get_swift_objects(connection, container):
    object_set = set()
    objects = connection.get_container(container=container,
                                       full_listing=True)[1]
    for obj in objects:
        try:
            name = strip_segment(obj['name'])
        except Exception as e:
            print(e)
        object_set.add(name)
    return object_set


def collect_args():
    parser = argparse.ArgumentParser(description='Glance Audit.')

    parser.add_argument('-f', '--for-realsies', action='store_true',
                        default=False, help="Actually delete things")
    parser.add_argument('-i', '--image-endpoint', action='store',
                        default=None, required=False,
                        help="Override image endpoint")
    parser.add_argument('-p', '--glance-project-id', action='store',
                        help="Glance project ID")
    return parser.parse_args()


if __name__ == '__main__':
    args = collect_args()
    noop = True
    if args.for_realsies:
        noop = False
        print("Running for realsies!!")
    else:
        print("Running Audit in noop mode, use -f to actually delete things")

    glance_project_id = args.glance_project_id
    k_session = get_session()
    connection = get_swift_client(k_session, project_id=glance_project_id)
    gc = get_glance_client(k_session, endpoint=args.image_endpoint)

    try:
        s_glance = get_swift_objects(connection, 'glance')
    except Exception:
        s_glance = set([])
    try:
        s_images = get_swift_objects(connection, 'images')
    except Exception:
        s_images = set([])
    print("Swift: Found %s images in glance container" % len(s_glance))
    print("Swift: Found %s images in images container" % len(s_images))
    g_glance = set()
    g_images = set()

    images = gc.images.list(visibility='all')
    for image in images:
        try:
            url = image.direct_url
        except Exception:
            continue
        container = url.split('/')[-2]
        object_name = url.split('/')[-1]
        if container == 'images':
            g_images.add(object_name)
        elif container == 'glance':
            g_glance.add(object_name)
        else:
            continue
    print("Glance: Found %s images in glance" % len(g_glance))
    print("Glance: Found %s images in images" % len(g_images))
    print()
    print("Deleting all orphaned swift data")
    bytes_deleted1 = delete_image_set(gc, connection, s_images - g_images,
                                      'images', noop=noop)

    bytes_deleted2 = delete_image_set(gc, connection, s_glance - g_glance,
                                      'glance', noop=noop)
    total_size = (bytes_deleted1 + bytes_deleted2) / 1024 / 1024 / 1024
    print("Total size deleted %sGB" % total_size)
    print()
    # Print out images where data is missing in swift
    missing = (g_images - s_images) | (g_glance - s_glance)
    print("Listing image IDs where data is missing in swift")
    for image_id in missing:
        print(image_id)
