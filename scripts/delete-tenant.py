#!/usr/bin/env python

import argparse
import swiftclient
import auth
import csv
from keystoneclient.exceptions import NotFound


def collect_args():

    parser = argparse.ArgumentParser(description='Deletes a Tenant')
    #parser.add_argument('-u', '--user', metavar='user', type=str,
    #                    required=False,
    #                    help='user to delete')
    parser.add_argument('-t', '--tenant', metavar='tenant', type=str,
                        required=False,
                        help='tenant to delete')
    parser.add_argument('-f', '--filename', metavar='filename',
            type=argparse.FileType('r'), required=False,
            help='file path with a list of tenants')
    parser.add_argument('-y', '--no-dry-run', action='store_true',
                        required=False,
                        help='Perform the actual actions, default is to only show what would happen')
    parser.add_argument('-1', '--stage1', action='store_true',
                        required=False,
                        help='Stage 1 Nag')
    parser.add_argument('-2', '--stage2', action='store_true',
                        required=False,
                        help='Stage 2 Termination')
    parser.add_argument('-3', '--stage3', action='store_true',
                        required=False,
                        help='Stage 3 Archive')

    return parser


def stage2_instances(client, dry_run=True, *tenants):

    """ =========  Nova Data  ==============
    """

    for tenant in tenants:
        instances = client.servers.list(search_opts={'tenant_id': tenant,
                                                    'all_tenants': 1})
        tenant_obj = kc.tenants.get(tenant)

        print "%d instance%s found for %s - %s" % (len(instances),
                "s"[len(instances)==1:], tenant, tenant_obj.name)
        if instances:
            for instance in instances:
                print "Instance ID", instance.id
                #instance_backup(instance, dry_run)
                instance_suspend(instance, dry_run)
                instance_lock(instance, dry_run)

        # TODO Backup filesystem, compress and store somewhere
        # for potential access otherwise delete instance


def stage2_volumes(client, dry_run=True, *tenants):

    """ =========  Cinder Data  ============
    """

    volumes = []
    all_volumes = client.volumes.list(search_opts={'all_tenants': 1})
    for tenant in tenants:
        for volume in all_volumes:
            vol_tenant = getattr(volume, "os-vol-tenant-attr:tenant_id", None)
            # There could be a better way than checking each tenant ID
            if vol_tenant == tenant:
                volumes.append(volume)

        print "\n%d volume%s found for tenant ID %s" % (len(volumes),
                "s"[len(volumes)==1:], tenant)
        for volume in volumes:
                print "%s attachments: %s, bootable: %s, size: %sGB" % (volume.id,
                        volume.attachments, volume.bootable, volume.size)


def stage2_images(glance_client, nova_client, *tenants):

    """ =========  Glance Data  ============
    """

    images = []
    for tenant in tenants:
        #all_images = list(glance_client.images.list(owner=tenant))
        all_images = glance_client.images.list(owner=tenant)
        for image in all_images:
            # Glance client returns all images user can see so this is needed
            if image.owner == tenant:
                images.append(image)

    print "\n%d image%s found for tenant ID %s" % (len(images),
            "s"[len(images)==1:], tenant)
    for image in images:
        instances = nova_client.servers.list(search_opts={'image': image.id,
                                                        'all_tenants': 1})
        print "%s public: %s, instances: %s" % (image.id, image.is_public,
                len(instances))

    # TODO Option to delete all images that have no running
    # instances. What if instances are in same tenant and will be
    # deleted though?


def stage2_objects(auth_url, token, swift_url, dry_run=True, *tenants):

    """ =========  Swift Data  =============
    """

    for tenant in tenants:
        swift_auth = 'AUTH_' + tenant
        swift_url = swift_url + swift_auth
        account_details = swiftclient.head_account(swift_url, token)
        containers = int(account_details['x-account-container-count'])

    print "\n%d container%s found for tenant ID %s" % (containers,
            "s"[containers==1:], tenant)

    if containers:
        bytes_used = account_details['x-account-bytes-used']
        mb_used = float(bytes_used) / 1024 / 1024
        print "Containers: %s" % containers
        print "Objects   : %s" % account_details['x-account-object-count']
        print "Data used : %.2f MB" % mb_used

    # TODO Option to Archive all data
    # TODO Option to delete all data


def stage3_instances(client, dry_run=True, *tenants):

    """ =========  Nova Data  ==============
    """

    for tenant in tenants:
        instances = client.servers.list(search_opts={'tenant_id': tenant,
                                                    'all_tenants': 1})
        print "%d instance%s found for tenant ID %s\n" % (len(instances),
                "s"[len(instances)==1:], tenant)
        if instances:
            for instance in instances:
                print "Instance ID", instance.id
                instance_delete(instance, dry_run)


def stage3_volumes(client, dry_run=True, *tenants):

    """ =========  Cinder Data  ============
    """
    volumes = []
    # Below should work but doesn't :(
    #volumes = client.volumes.list(search_opts={'os-vol-tenant-attr:tenant_id': tenant_id,
    #                                            'all_tenants': 1})
    volumes = client.volumes.list(search_opts={'all_tenants': 1})
    for tenant in tenants:
        for volume in volumes:
            vol_tenant= getattr(volume, "os-vol-tenant-attr:tenant_id", None)
            if vol_tenant == tenant:
                volumes.append(volume)

        print "\n%d volume%s found for tenant ID %s" % (len(volumes),
                "s"[len(volumes)==1:], tenant)
        for volume in volumes:
            print "%s attachments: %s, bootable: %s, size: %sGB" % (volume.id,
                    volume.attachments, volume.bootable, volume.size)
            if not dry_run:
                volume_delete(volume, dry_run=dry_run)


def stage3_keystone(client, tenant_id, dry_run=True):

    """ ===== Keystone Data (tenant) =======
    """

    try:
        print "Deleting tenant", tenant_id
        if not dry_run:
            client.tenants.update(tenant_id, status='suspended')
    except NotFound as e:
        print e, '\n'


def instance_suspend(instance, dry_run=True):

    print "Suspending instance..."
    if not dry_run:
        if instance.status == 'SUSPENDED':
            print "Instance is already suspended."
        elif instance.status == 'SHUTOFF':
            print "Instance is off"
        else:
            instance.suspend()


def instance_backup(instance, dry_run=True):

    print "Backing up..."
    if not dry_run:
        instance.create_image(instance.id)


def instance_lock(instance, dry_run=True):

    print "Locking instance..."
    if not dry_run:
        instance.lock()


def instance_delete(instance, dry_run=True):

    print "Deleting instance..."
    if not dry_run:
        instance.delete()


def volume_delete(volume, dry_run=True):

    print "Deleting volume..."
    if not dry_run:
        volume.delete()


if __name__ == '__main__':

    args = collect_args().parse_args()

    if args.no_dry_run:
        dry_run = False
    else:
        dry_run = True

    kc = auth.get_keystone_client()
    token = kc.auth_token
    auth_url = kc.auth_url
    catalog = kc.service_catalog
    glance_url = catalog.url_for(service_type='image')
    # Currently keystone returns version number in glance endpoint URL,
    # so we remove it because it gets set by glanceclient itself
    if glance_url.endswith('v1'):
        glance_url = glance_url[:-2]
    gc = auth.get_glance_client(glance_url, token)
    nc = auth.get_nova_client()
    cc = auth.get_cinder_client()

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
        stage2_instances(nc, dry_run, *tenants)
        stage2_volumes(cc, dry_run, *tenants)
        stage2_images(gc, nc, *tenants)
        if swift_url:
            stage2_objects(auth_url, token, swift_url, dry_run, *tenants)
    if args.stage3:
        stage3_instances(nc, dry_run, *tenants)
        stage3_volumes(cc, dry_run, *tenants)
        stage3_keystone(kc, *tenants)
        #if user_id:
        #    stage3_keystone_user(kc, tenant_id)
