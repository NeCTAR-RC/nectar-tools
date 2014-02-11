#!/usr/bin/env python

import argparse
import swiftclient
import auth
import csv
from keystoneclient.exceptions import NotFound


DRY_RUN = True


def collect_args():

    parser = argparse.ArgumentParser(description='Deletes a Tenant')
    parser.add_argument('-t', '--tenant', metavar='tenant', type=str,
                        help='Tenant to delete')
    parser.add_argument('-f', '--filename', metavar='filename',
                        type=argparse.FileType('r'),
                        help='File path with a list of tenants')
    parser.add_argument('-y', '--no-dry-run', action='store_true',
                        default=False,
                        help='Perform the actual actions, default is to only show what would happen')
    parser.add_argument('-1', '--stage1', action='store_true',
                        help='Stage 1 Nag')
    parser.add_argument('-2', '--stage2', action='store_true',
                        help='Stage 2 Termination')
    parser.add_argument('-3', '--stage3', action='store_true',
                        help='Stage 3 Archive')

    return parser


def stage2_instances(client, tenant):

    """ =========  Nova Data  ==============
    """

    instances = client.servers.list(search_opts={'tenant_id': tenant,
                                                'all_tenants': 1})
    print "%d instance%s" % (len(instances), "s"[len(instances)==1:])
    if instances:
        for instance in instances:
            print "Instance ID", instance.id
            # TODO Backup filesystem, compress and store somewhere
            #instance_backup(instance)
            instance_suspend(instance)
            instance_lock(instance)


def stage2_volumes(client, tenant, all_volumes):

    """ =========  Cinder Data  ============
    """

    volumes = []
    for volume in all_volumes:
        vol_tenant = getattr(volume, "os-vol-tenant-attr:tenant_id", None)
        # There could be a better way than checking each tenant ID
        if vol_tenant == tenant:
            volumes.append(volume)

    print "%d volume%s" % (len(volumes), "s"[len(volumes)==1:])
    for volume in volumes:
            print "%s attachments: %s, bootable: %s, size: %sGB" % (volume.id,
                    volume.attachments, volume.bootable, volume.size)


def stage2_images(glance_client, nova_client, tenant, all_images):

    """ =========  Glance Data  ============
    """

    images = []
    for image in all_images:
        # Glance client returns all images user can see so this is needed
        if image.owner == tenant:
            images.append(image)

    print "%d image%s" % (len(images), "s"[len(images)==1:])
    for image in images:
        instances = nova_client.servers.list(search_opts={'image': image.id,
                                                        'all_tenants': 1})
        print "%s public: %s, instances: %s" % (image.id, image.is_public,
                len(instances))

    # TODO Option to delete all images that have no running
    # instances. What if instances are in same tenant and will be
    # deleted though?


def stage2_objects(auth_url, token, swift_url, tenant):

    """ =========  Swift Data  =============
    """

    swift_auth = 'AUTH_' + tenant
    swift_url = swift_url + swift_auth
    account_details = swiftclient.head_account(swift_url, token)
    containers = int(account_details['x-account-container-count'])

    print "%d container%s" % (containers, "s"[containers==1:])
    if containers:
        bytes_used = account_details['x-account-bytes-used']
        mb_used = float(bytes_used) / 1024 / 1024
        print "Containers: %s" % containers
        print "Objects   : %s" % account_details['x-account-object-count']
        print "Data used : %.2f MB" % mb_used

    # TODO Option to Archive all data
    # TODO Option to delete all data


def stage3_instances(client, tenant):

    """ =========  Nova Data  ==============
    """

    instances = client.servers.list(search_opts={'tenant_id': tenant,
                                                'all_tenants': 1})
    print "%d instance%s found for tenant ID %s\n" % (len(instances),
            "s"[len(instances)==1:], tenant)
    if instances:
        for instance in instances:
            print "Instance ID", instance.id
            instance_delete(instance)


def stage3_volumes(client, tenant):

    """ =========  Cinder Data  ============
    """
    volumes = []
    # Below should work but doesn't :(
    #volumes = client.volumes.list(search_opts={'os-vol-tenant-attr:tenant_id': tenant_id,
    #                                            'all_tenants': 1})
    volumes = client.volumes.list(search_opts={'all_tenants': 1})
    for volume in volumes:
        vol_tenant= getattr(volume, "os-vol-tenant-attr:tenant_id", None)
        if vol_tenant == tenant:
            volumes.append(volume)

    print "\n%d volume%s found for tenant ID %s" % (len(volumes),
            "s"[len(volumes)==1:], tenant)
    for volume in volumes:
        print "%s attachments: %s, bootable: %s, size: %sGB" % (volume.id,
                volume.attachments, volume.bootable, volume.size)
        if not DRY_RUN:
            volume_delete(volume)


def stage3_keystone(client, tenant, status):

    """ ===== Keystone Data (tenant) =======
    """

    try:
        print "Suspending tenant", tenant
        if status == 'suspended':
            print "Tenant is already suspended."
        else:
            if not DRY_RUN:
                client.tenants.update(tenant, status='suspended')
    except NotFound as e:
        print e, '\n'


def instance_suspend(instance):

    print "Suspending instance..."
    if instance.status == 'SUSPENDED':
        print "Instance is already suspended."
    elif instance.status == 'SHUTOFF':
        print "Instance is off"
    else:
        if not DRY_RUN:
            instance.suspend()


def instance_backup(instance):

    print "Backing up..."
    if not DRY_RUN:
        instance.create_image(instance.id)


def instance_lock(instance):

    print "Locking instance..."
    if not DRY_RUN:
        instance.lock()


def instance_delete(instance):

    print "Deleting instance..."
    if not DRY_RUN:
        instance.delete()


def volume_delete(volume):

    print "Deleting volume..."
    if not DRY_RUN:
        volume.delete()


if __name__ == '__main__':

    args = collect_args().parse_args()
    if args.no_dry_run:
        DRY_RUN = False 

    kc = auth.get_keystone_client()
    token = kc.auth_token
    auth_url = kc.auth_url
    catalog = kc.service_catalog
    glance_url = catalog.url_for(service_type='image')
    # Currently keystone returns version number in glance endpoint URL,
    # so we remove it because it gets set by glanceclient itself
    glance_url = glance_url.rstrip('v1')
    gc = auth.get_glance_client(glance_url, token)
    nc = auth.get_nova_client()
    cc = auth.get_cinder_client()
    all_volumes = cc.volumes.list(search_opts={'all_tenants': 1})

    tenants = []
    if args.tenant:
        tenants.append(args.tenant)
    if args.filename:
        reader = csv.reader(args.filename)
        for row in reader:
            tenants.append(row[0])

    if catalog.get_endpoints(service_type='object-store',
                             endpoint_type='adminURL'):
        swift_url = catalog.url_for(service_type='object-store',
                                    endpoint_type='adminURL')
    else:
        swift_url = None

    if args.stage1:
        print "Would send email"
        #render_email()
        #exit
    if args.stage2:
        for tenant in tenants:
            tenant_obj = kc.tenants.get(tenant)
            print ':: Tenant ID', tenant, '-', tenant_obj.name
            stage2_instances(nc, tenant)
            stage2_volumes(cc, tenant, all_volumes)
            # TODO takes so long to find images atm
            # need to find a better way
            #all_images = gc.images.list(owner=tenant)
            #stage2_images(gc, nc, tenant, all_images)
            if swift_url:
                stage2_objects(auth_url, token, swift_url, tenant)
            print
    if args.stage3:
        for tenant in tenants:
            tenant_obj = kc.tenants.get(tenant)
            #stage3_instances(nc, *tenants)
            #stage3_volumes(cc, *tenants)
            stage3_keystone(kc, tenant, tenant_obj.status)
            print
