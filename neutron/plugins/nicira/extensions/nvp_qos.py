# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Nicira, Inc.
# All Rights Reserved
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Aaron Rosen, Nicira Networks, Inc.


from abc import abstractmethod

from neutron.api import extensions
from neutron.api.v2 import attributes as attr
from neutron.api.v2 import base
from neutron.common import exceptions as qexception
from neutron import manager


# For policy.json/Auth
qos_queue_create = "create_qos_queue"
qos_queue_delete = "delete_qos_queue"
qos_queue_get = "get_qos_queue"
qos_queue_list = "get_qos_queues"


class DefaultQueueCreateNotAdmin(qexception.InUse):
    message = _("Need to be admin in order to create queue called default")


class DefaultQueueAlreadyExists(qexception.InUse):
    message = _("Default queue already exists.")


class QueueInvalidDscp(qexception.InvalidInput):
    message = _("Invalid value for dscp %(data)s must be integer value"
                " between 0 and 63.")


class QueueMinGreaterMax(qexception.InvalidInput):
    message = _("Invalid bandwidth rate, min greater than max.")


class QueueInvalidBandwidth(qexception.InvalidInput):
    message = _("Invalid bandwidth rate, %(data)s must be a non negative"
                " integer.")


class QueueNotFound(qexception.NotFound):
    message = _("Queue %(id)s does not exist")


class QueueInUseByPort(qexception.InUse):
    message = _("Unable to delete queue attached to port.")


class QueuePortBindingNotFound(qexception.NotFound):
    message = _("Port is not associated with lqueue")


def convert_to_unsigned_int_or_none(val):
    if val is None:
        return
    try:
        val = int(val)
        if val < 0:
            raise ValueError
    except (ValueError, TypeError):
        msg = _("'%s' must be a non negative integer.") % val
        raise qexception.InvalidInput(error_message=msg)
    return val


def convert_to_unsigned_int_or_none_max_63(val):
    val = convert_to_unsigned_int_or_none(val)
    if val > 63:
        raise QueueInvalidDscp(data=val)
    return val

# As per NVP API, if a queue is trusted, DSCP must be omitted; if a queue is
# untrusted, DSCP must be specified. Whichever default values we choose for
# the tuple (qos_marking, dscp), there will be at least one combination of a
# request with conflicting values: for instance, with the following default:
#
# qos_marking = 'untrusted', dscp = '0'
#
# requests with qos_marking = 'trusted' and a default dscp will fail. Since
# it is convoluted to ask the admin to specify a None value for dscp when
# qos_marking is 'trusted', it is best to ignore the dscp value, regardless
# of whether it has been specified or not. This preserves the chosen default
# and keeps backward compatibility with the API. A warning will be logged, as
# the server is overriding a potentially conflicting request from the admin
RESOURCE_ATTRIBUTE_MAP = {
    'qos_queues': {
        'id': {'allow_post': False, 'allow_put': False,
               'is_visible': True},
        'default': {'allow_post': True, 'allow_put': False,
                    'convert_to': attr.convert_to_boolean,
                    'is_visible': True, 'default': False},
        'name': {'allow_post': True, 'allow_put': False,
                 'validate': {'type:string': None},
                 'is_visible': True, 'default': ''},
        'min': {'allow_post': True, 'allow_put': False,
                'is_visible': True, 'default': '0',
                'convert_to': convert_to_unsigned_int_or_none},
        'max': {'allow_post': True, 'allow_put': False,
                'is_visible': True, 'default': None,
                'convert_to': convert_to_unsigned_int_or_none},
        'qos_marking': {'allow_post': True, 'allow_put': False,
                        'validate': {'type:values': ['untrusted', 'trusted']},
                        'default': 'untrusted', 'is_visible': True},
        'dscp': {'allow_post': True, 'allow_put': False,
                 'is_visible': True, 'default': '0',
                 'convert_to': convert_to_unsigned_int_or_none_max_63},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'required_by_policy': True,
                      'validate': {'type:string': None},
                      'is_visible': True},
    },
}


QUEUE = 'queue_id'
RXTX_FACTOR = 'rxtx_factor'
EXTENDED_ATTRIBUTES_2_0 = {
    'ports': {
        RXTX_FACTOR: {'allow_post': True,
                      # FIXME(arosen): the nvp plugin currently does not
                      # implement updating rxtx factor on port.
                      'allow_put': True,
                      'is_visible': False,
                      'default': 1,
                      'enforce_policy': True,
                      'convert_to': convert_to_unsigned_int_or_none},

        QUEUE: {'allow_post': False,
                'allow_put': False,
                'is_visible': True,
                'default': False,
                'enforce_policy': True}},
    'networks': {QUEUE: {'allow_post': True,
                         'allow_put': True,
                         'is_visible': True,
                         'default': False,
                         'enforce_policy': True}}

}


class Nvp_qos(object):
    """Port Queue extension."""

    @classmethod
    def get_name(cls):
        return "nvp-qos"

    @classmethod
    def get_alias(cls):
        return "nvp-qos"

    @classmethod
    def get_description(cls):
        return "NVP QoS extension."

    @classmethod
    def get_namespace(cls):
        return "http://docs.openstack.org/ext/nvp-qos/api/v2.0"

    @classmethod
    def get_updated(cls):
        return "2012-10-05T10:00:00-00:00"

    @classmethod
    def get_resources(cls):
        """Returns Ext Resources."""
        exts = []
        plugin = manager.NeutronManager.get_plugin()
        resource_name = 'qos_queue'
        collection_name = resource_name.replace('_', '-') + "s"
        params = RESOURCE_ATTRIBUTE_MAP.get(resource_name + "s", dict())
        controller = base.create_resource(collection_name,
                                          resource_name,
                                          plugin, params, allow_bulk=False)

        ex = extensions.ResourceExtension(collection_name,
                                          controller)
        exts.append(ex)

        return exts

    def get_extended_resources(self, version):
        if version == "2.0":
            return dict(EXTENDED_ATTRIBUTES_2_0.items() +
                        RESOURCE_ATTRIBUTE_MAP.items())
        else:
            return {}


class QueuePluginBase(object):
    @abstractmethod
    def create_qos_queue(self, context, queue):
        pass

    @abstractmethod
    def delete_qos_queue(self, context, id):
        pass

    @abstractmethod
    def get_qos_queue(self, context, id, fields=None):
        pass

    @abstractmethod
    def get_qos_queues(self, context, filters=None, fields=None):
        pass
