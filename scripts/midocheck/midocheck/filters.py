class BaseFilter:
    @staticmethod
    def mido(resource):
        return True

    @staticmethod
    def midoneutron(resource):
        return True

    @staticmethod
    def neutron(resource):
        return True


class RouterFilter(BaseFilter):
    @staticmethod
    def mido(resource):
        # load balancers are represented as routers in mido, ignore them
        if resource.get_load_balancer_id() is not None:
            return False

        return True


class PortFilter(BaseFilter):
    @staticmethod
    def mido(resource):
        if resource.get_type() != 'Bridge':
            return False

        return True

    @staticmethod
    def midoneutron(resource):
        # midonet uplink ports
        if resource.get('device_owner') == 'network:router_interface' and \
           resource.get('binding:profile').get('interface_name') is not None:
            return False

        return True

    @staticmethod
    def neutron(resource):
        # fixed ip ports
        if resource.binding_vif_type == 'bridge':
            return False

        # midonet uplink ports
        if resource.device_owner == 'network:router_interface' and \
           'interface_name' in resource.binding_profile:
            return False

        # floating ips do not have a mido representation
        if resource.device_owner == 'network:floatingip':
            return False

        return True
