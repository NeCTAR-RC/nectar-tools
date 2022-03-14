#!/usr/bin/env python

def get_ct_create (ctconfig):
    name = ctconfig.name
    az = ctconfig.az
    network = ctconfig.network
    flavor = ctconfig.flavor

    str_cluster_template_create = "openstack coe cluster template create --coe kubernetes --image fedora-coreos-32 --volume-driver cinder --master-flavor {flavor} --flavor {flavor} --docker-storage-driver overlay2 --floating-ip-disable --master-lb-enabled --external-network {network} --labels container_infra_prefix=registry.rc.nectar.org.au/nectarmagnum/,kube_tag=v1.21.1,flannel_tag=v0.14.0-amd64,master_lb_floating_ip_enabled=true,cinder_csi_enabled=true,docker_volume_type=standard,availability_zone={az},ingress_controller=octavia kubernetes-{name}-v1.21.1 --public"
    return str_cluster_template_create.format(name=name, az=az, network=network, flavor=flavor)

# config for a CT
class CTConfig:
    def __init__(self, name, az=None, network=None, flavor='m3.small'):
        self.name = name
        # defaults to name
        self.az = az or name
        # defaults to name
        self.network = network or name
        self.flavor = flavor


ctconfigs = [CTConfig('melbourne', az='melbourne-qh2'),
             CTConfig('melbourne-qh2-uom', network='melbourne', flavor='uom.general.2c8g'),
             CTConfig('monash-01', network='monash'),
             CTConfig('monash-02', network='monash'),
             CTConfig('intersect', network='QRIScloud'),
             CTConfig('tasmania'),
             CTConfig('auckland'),
             CTConfig('QRIScloud'),
             CTConfig('swinburne-01', network='swinburne'),
            ]

for ctconfig in ctconfigs:
    print (get_ct_create(ctconfig))

print('---------------------------------------------------------------------------------')

ctconfigs = [CTConfig('coreservices'),
             CTConfig('qh2-test', network='qh2-test-floating'),
            ]

for ctconfig in ctconfigs:
    print (get_ct_create(ctconfig))

print('---------------------------------------------------------------------------------')

ctconfigs = [CTConfig('lani', network='public'),
             CTConfig('luna', network='public'),
            ]

for ctconfig in ctconfigs:
    print (get_ct_create(ctconfig))
