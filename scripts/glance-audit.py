#!/usr/bin/env python

"""
Does an audit of glance and it's swift image store.
It will remove all swift objects that should't be there.

You will need to run this with the same creds as what Glance API
uses.

"""
import argparse
import swiftclient
import glanceclient as glance_client
from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
import os
import sys
import httplib

SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'

def get_swift_connection():
    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    return swiftclient.Connection(
        auth_url, auth_username, auth_password,
        tenant_name=auth_tenant,
        auth_version='2')


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
            if e.http_status != httplib.NOT_FOUND:
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
                    print "Deleted %s/%s" % (obj_container, segment['name'])
                except swiftclient.ClientException as e:
                    msg = 'Unable to delete segment %(segment_name)s'
                    msg = msg % {'segment_name': segment['name']}
                    print msg
                    segment_error = True
        if not segment_error:
            # Only delete the manifest if no segment errors
            # Delete object (or, in segmented case, the manifest)
            if not noop:
                connection.delete_object(container, obj)
            print "Deleted %s/%s" % (container, obj)

    except swiftclient.ClientException as e:
        if e.http_status == httplib.NOT_FOUND:
            msg = "Swift could not find image at URI. %s/%s"
            print msg % (container, obj)
            if not noop:
                shotgun_segments(connection, container, obj)
        else:
            print e
    return size


def shotgun_segments(connection, container, image_id):
    limit = 100
    segment = 1
    while segment < limit:
        obj = "%s-%05d" % (image_id, segment)
        try:
            connection.delete_object(container, obj)
            print "Deleted %s/%s" % (container, obj)
        except swiftclient.ClientException as e:
            if e.http_status == httplib.NOT_FOUND:
                pass
            else:
                print e
        segment += 1


def get_keystone_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')
    try:
        kc = ks_client.Client(username=auth_username,
                              password=auth_password,
                              tenant_name=auth_tenant,
                              auth_url=auth_url)
    except AuthorizationFailure as e:
        print e
        print 'Authorization failed, have you sourced your openrc?'
        sys.exit(1)
    return kc


def get_glance_client(kc, api_version=2, endpoint=None):
    if endpoint is None:
        image_endpoint = kc.service_catalog.url_for(service_type='image')
        image_endpoint = image_endpoint.replace('v1', '')
    else:
        image_endpoint = endpoint
    gc = glance_client.Client(api_version, image_endpoint, token=kc.auth_token)
    return gc


def delete_image_set(gc, image_set, container, noop=True):
    bytes_deleted = 0
    connection = get_swift_connection()
    for image_id in image_set:
        delete = False
        try:
            image = gc.images.get(image_id)
            if image.deleted or image.status == 'killed':
                delete = True
            else:
                print "Skipping active image %s" % image_id
                print "Status: %s" % image.status
                print "Created: %s, Updated %s" % (image.created_at,
                                                   image.updated_at)

        except glance_client.exc.HTTPNotFound:
            delete = True
        if delete:
            size = delete_swift_image(connection, container,
                                      image_id, noop)
            bytes_deleted += size
    return bytes_deleted


def strip_segment(name):
    """ Strips out segment part from image objects
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
        except Exception, e:
            print e
        object_set.add(name)
    return object_set


def collect_args():
    parser = argparse.ArgumentParser(description='Glance Audit.')

    parser.add_argument('-f', '--for-realsies', action='store_true',
                        default=False, help="Actually delete things")
    parser.add_argument('-i', '--image-endpoint', action='store',
                        default=None, required=False,
                        help="Override image endpoint")
    return parser.parse_args()


if __name__ == '__main__':
    args = collect_args()
    noop = True
    if args.for_realsies:
        noop = False
        print "Running for realsies!!"
    else:
        print "Running Audit in noop mode, use -f to actually delete things"
    kc = get_keystone_client()
    connection = get_swift_connection()
    image_endpoint = args.image_endpoint
    gc = get_glance_client(kc, endpoint=image_endpoint)
    gc1 = get_glance_client(kc, api_version=1, endpoint=image_endpoint)

    s_glance = get_swift_objects(connection, 'glance')
    s_images = get_swift_objects(connection, 'images')
    print "Swift: Found %s images in glance container" % len(s_glance)
    print "Swift: Found %s images in images container" % len(s_images)
    g_glance = set()
    g_images = set()
    images = list(gc.images.list(is_public=None))
    for image in images:
        try:
            url = image.direct_url
        except:
            continue
        container = url.split('/')[-2]
        object_name = url.split('/')[-1]
        if container == 'images':
            g_images.add(object_name)
        elif container == 'glance':
            g_glance.add(object_name)
        else:
            continue
    print "Glance: Found %s images in glance container" % len(g_glance)
    print "Glance: Found %s images in images container" % len(g_images)
    print
    print "Deleting all orphaned swift data"
    bytes_deleted1 = delete_image_set(gc1, s_images - g_images,
                                      'images', noop=noop)
    bytes_deleted2 = delete_image_set(gc1, s_glance - g_glance,
                                      'glance', noop=noop)
    total_size = (bytes_deleted1 + bytes_deleted2) / 1024 / 1024 / 1024
    print "Total size deleted %sGB" % total_size
    print
    # Print out images where data is missing in swift
    missing = (g_images - s_images) | (g_glance - s_glance)
    print "Listing image IDs where data is missing in swift"
    for image_id in missing:
        print image_id
