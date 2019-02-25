# -*- coding: utf-8 -*-

from prettytable import PrettyTable

from midocheck import filters


# A Resource is a container for neutron, midoneutron and mido resources
# of the same uuid
class Resource:
    def __init__(self, uuid):
        self.id = uuid

        # a resource in neutron
        self.neutron = None

        # a neutron style resource in midonet - this acts like a mapping
        # between neutron and midonet resources
        self.midoneutron = None

        # a resource in midonet - use for flows, etc
        self.mido = None

        self.delete_flag = False


# A dict of Resource, with key being Resource's uuid. It holds a blacklist
# of resource uuids that cannot be handled by midocheck.
class Resources(dict):
    def __init__(self):
        self.__name__ = 'Resources'

        # list of uuids that midocheck cannot handle
        self.blacklist_uuids = []

        # overwrite these with filters in subclasses
        self.filter = None

    def get_or_create(self, uuid):
        if self.get(uuid) is None:
            return self.create(uuid)
        return self.get(uuid)

    def create(self, uuid):
        raise NotImplementedError

    # TODO: have just one add() and determine what to do by class of resource
    # being added
    # adds mido type resource to the list of resources
    def add_mido(self, mido):
        for i in mido:
            uuid = i.get_id()
            if uuid in self.blacklist_uuids:
                next
            if self.filter.mido(i):
                r = self.get_or_create(uuid)
                r.mido = i
            else:
                self.blacklist_uuids.append(uuid)

    # adds midoneutron type resource to the list of resources
    def add_midoneutron(self, midoneutron):
        for i in midoneutron:
            uuid = i.get('id')
            if uuid in self.blacklist_uuids:
                next
            if self.filter.midoneutron(i):
                r = self.get_or_create(uuid)
                r.midoneutron = i
            else:
                self.blacklist_uuids.append(uuid)

    # adds neutron type resource to the list of resources
    def add_neutron(self, neutron):
        for i in neutron:
            uuid = i.get('id')
            if uuid in self.blacklist_uuids:
                next
            if self.filter.neutron(i):
                r = self.get_or_create(uuid)
                r.neutron = i
            else:
                self.blacklist_uuids.append(uuid)

    def purge_blacklist(self):
        for uuid in self.blacklist_uuids:
            self.pop(uuid, None)

    def analyse(self):
        for k, v in self.items():
            if v.neutron is None and \
               (v.mido is not None or v.midoneutron is not None):
                v.delete_flag = True

    def get_delete_uuids(self):
        return [k for k, v in self.items() if v.delete_flag]

    def delete(self):
        for i in self.values():
            if i.delete_flag:
                i.delete()

    def prettyprint(self, show_all=True):

        t = PrettyTable()
        t.field_names = ['UUID', 'Neutron', 'MidonetNeutron', 'Midonet',
                         'delete?']

        for uuid in sorted(self):
            t.add_row([uuid,
                       'x' if self[uuid].neutron else '',
                       'x' if self[uuid].midoneutron else '',
                       'x' if self[uuid].mido else '',
                       '✓' if self[uuid].delete_flag else ''])

        print(t)


class Routers(Resources):
    def __init__(self):
        super().__init__()
        self.__name__ = 'Routers'
        self.filter = filters.RouterFilter

    def create(self, uuid):
        self[uuid] = Resource(uuid)
        return self.get(uuid)


class Ports(Resources):
    def __init__(self):
        super().__init__()
        self.__name__ = 'Ports'
        self.filter = filters.PortFilter

    def create(self, uuid):
        self[uuid] = Resource(uuid)
        return self.get(uuid)
