# lookup table from network and AZ to Site
#
# Used:
# o floating ip list --c 'Floating Network' -f value | sort | uniq | xargs -L1 openstack network show -c name -f value
# to get the networks (this will only list the floating networks)
#
# Used:
# gnocchi resource list --type site -c name -f value| sort | uniq
# to get the sites
#
# Used:
# o availability zone list -c 'Zone Name' -f value | sort | uniq
# to get the availability zones
#

NetworkToSite = {'public': 'luna',  #dev
                'coreservices': 'coreservices',  #rctest
                'qh2-test-floating': 'melbourne',
                'QRIScloud': 'QRIScloud' ,  #nectar
                'tasmania': 'tasmania',
                'qld': 'intersect',
                'swinburne': 'swinburne' ,
                'auckland': 'auckland',
                'qh2-uom': 'melbourne',
                'melbourne': 'melbourne',
                'qh2-uom-internal': 'melbourne',
                'monash-02': 'monash',
                'monash-01': 'monash',
                'monash': 'monash'
                }

AZToSite = {'lani': 'lani',  #dev
            'luna': 'luna',
            'bogus': 'unknown',
            'coreservices': 'coreservices',  #rctest
            'qh2-test-floating': 'melbourne',
            'auckland': 'auckland',  #nectar
            'intersect': 'intersect',
            'melbourne-qh2': 'melbourne',
            'melbourne-qh2-uom': 'melbourne',
            'monash-01': 'monash',
            'monash-02': 'monash',
            'monash-03': 'monash',
            'QRIScloud': 'QRIScloud',
            'swinburne-01': 'swinburne',
            'tasmania': 'tasmania',
            'tasmania-02': 'tasmania',
            'tasmania-s': 'tasmania',
            'internal': 'unknown',  #shared
            'nova': 'unknown'
            }