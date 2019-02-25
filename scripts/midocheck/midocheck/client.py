# -*- coding: utf-8 -*-

import logging
import os
import openstack
import webob

from midonetclient.api import MidonetApi
from midonetclient.client import MidonetClient

from midocheck import resource

LOG = logging.getLogger(__name__)


class Client:
    def __init__(self):
        # clients
        self.openstack_client = openstack_client()
        self.midonet_api = midonet_api()
        self.midonet_client = midonet_client()

    def openstack_client():
        return openstack.connect(cloud='envvars')

    def midonet_client():
        client = MidonetClient(os.getenv('MIDO_API_URL'),
                               os.getenv('MIDO_USER'),
                               os.getenv('MIDO_PASSWORD'),
                               os.getenv('MIDO_PROJECT_ID'))
        return client

    def midonet_api():
        client = MidonetApi(os.getenv('MIDO_API_URL'), os.getenv('MIDO_USER'),
                            os.getenv('MIDO_PASSWORD'),
                            os.getenv('MIDO_PROJECT_ID'))
        return client

    def list_routers(self, uuids=[]):
        mido = self.midonet_api.get_routers()
        midoneutron = self.midonet_client.get_routers()
        neutron = list(self.openstack_client.network.routers())

        resources = resource.Routers()
        resources.add_mido(mido)
        resources.add_midoneutron(midoneutron)
        resources.add_neutron(neutron)
        resources.purge_blacklist()

        return resources

    def list_ports(self, uuids=[]):
        mido = self.midonet_api.get_ports()
        midoneutron = self.midonet_client.get_ports()
        neutron = list(self.openstack_client.network.ports())

        resources = resource.Ports()
        resources.add_mido(mido)
        resources.add_midoneutron(midoneutron)
        resources.add_neutron(neutron)
        resources.purge_blacklist()

        return resources

    # just try deleting
    def delete_routers(self, uuids):
        for uuid in uuids:
            print("Deleting router {}".format(uuid))
            try:
                self.midonet_client.delete_router(uuid)
            except webob.exc.HTTPNotFound:
                LOG.error("Unable to delete midoneutron resource {} due to "
                          "missing dependent resources".format(uuid))
                try:
                    self.midonet_api.delete_router(uuid)
                except webob.exc.HTTPNotFound:
                    LOG.error("Unable to delete mido resource {}".format(uuid))

    def delete_ports(self, uuids):
        for uuid in uuids:
            print("Deleting port {}".format(uuid))
            try:
                self.midonet_client.delete_port(uuid)
            except webob.exc.HTTPNotFound:
                LOG.error("Unable to delete midoneutron resource {}".
                          format(uuid))
                try:
                    self.midonet_api.delete_port(uuid)
                except:
                    LOG.error("Unable to delete mido resource {}".format(uuid))

    @staticmethod
    def _filter_mido(self, mido):
        raise NotImplementedError


def openstack_client():
    return openstack.connect(cloud='envvars')


def midonet_client():
    client = MidonetClient(os.getenv('MIDO_API_URL'), os.getenv('MIDO_USER'),
                           os.getenv('MIDO_PASSWORD'),
                           os.getenv('MIDO_PROJECT_ID'))
    return client


def midonet_api():
    client = MidonetApi(os.getenv('MIDO_API_URL'), os.getenv('MIDO_USER'),
                        os.getenv('MIDO_PASSWORD'),
                        os.getenv('MIDO_PROJECT_ID'))
    return client
