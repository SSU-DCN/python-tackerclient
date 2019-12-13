# Copyright (C) 2020 NTT DATA
# All Rights Reserved.
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

import json
import logging
import os
import time

from osc_lib.cli import format_columns
from osc_lib.command import command
from osc_lib import utils

from tackerclient.common import exceptions
from tackerclient.i18n import _
from tackerclient.osc import sdk_utils

LOG = logging.getLogger(__name__)

_mixed_case_fields = ('vnfInstanceName', 'vnfInstanceDescription', 'vnfdId',
                      'vnfProvider', 'vnfProductName', 'vnfSoftwareVersion',
                      'vnfdVersion', 'instantiationState',
                      'vimConnectionInfo', 'instantiatedVnfInfo')

_VNF_INSTANCE = 'vnf_instance'

VNF_INSTANCE_TERMINATION_TIMEOUT = 300

EXTRA_WAITING_TIME = 10

SLEEP_TIME = 1


def _get_columns(vnflcm_obj, action=None):
    column_map = {
        'id': 'ID',
        'vnfInstanceName': 'VNF Instance Name',
        'vnfInstanceDescription': 'VNF Instance Description',
        'vnfdId': 'VNFD ID',
        'vnfProvider': 'VNF Provider',
        'vnfProductName': 'VNF Product Name',
        'vnfSoftwareVersion': 'VNF Software Version',
        'vnfdVersion': 'VNFD Version',
        'instantiationState': 'Instantiation State',
        '_links': 'Links',
    }
    if action == 'show':
        if vnflcm_obj['instantiationState'] == 'INSTANTIATED':
            column_map.update(
                {'instantiatedVnfInfo': 'Instantiated Vnf Info'}
            )
        column_map.update(
            {'vimConnectionInfo': 'VIM Connection Info',
             '_links': 'Links'}
        )
    return sdk_utils.get_osc_show_columns_for_sdk_resource(vnflcm_obj,
                                                           column_map)


class CreateVnfLcm(command.ShowOne):
    _description = _("Create a new VNF Instance")

    def get_parser(self, prog_name):
        parser = super(CreateVnfLcm, self).get_parser(prog_name)
        parser.add_argument(
            'vnfd_id',
            metavar="<vnfd-id>",
            help=_('Identifier that identifies the VNFD which defines the '
                   'VNF instance to be created.'))
        parser.add_argument(
            '--name',
            metavar="<vnf-instance-name>",
            help=_('Name of the VNF instance to be created.'))
        parser.add_argument(
            '--description',
            metavar="<vnf-instance-description>",
            help=_('Description of the VNF instance to be created.'))
        parser.add_argument(
            '--I',
            metavar="<param-file>",
            help=_("Instantiate VNF subsequently after it's creation. "
                   "Specify instantiate request parameters in a json file."))
        return parser

    def args2body(self, parsed_args, file_path=None):
        body = {}

        if file_path:
            return instantiate_vnf_args2body(file_path)

        body['vnfdId'] = parsed_args.vnfd_id

        if parsed_args.description:
            body['vnfInstanceDescription'] = parsed_args.description

        if parsed_args.name:
            body['vnfInstanceName'] = parsed_args.name

        return body

    def take_action(self, parsed_args):
        client = self.app.client_manager.tackerclient
        vnf = client.create_vnf_instance(self.args2body(parsed_args))
        if parsed_args.I:
            # Instantiate VNF instance.
            result = client.instantiate_vnf_instance(
                vnf['id'],
                self.args2body(parsed_args, file_path=parsed_args.I))
            if not result:
                print((_('VNF Instance %(id)s is created and instantiation'
                         ' request has been accepted.') % {'id': vnf['id']}))
        display_columns, columns = _get_columns(vnf)
        data = utils.get_item_properties(
            sdk_utils.DictModel(vnf),
            columns, mixed_case_fields=_mixed_case_fields)
        return (display_columns, data)


class ShowVnfLcm(command.ShowOne):
    _description = _("Display VNF instance details")

    def get_parser(self, prog_name):
        parser = super(ShowVnfLcm, self).get_parser(prog_name)
        parser.add_argument(
            _VNF_INSTANCE,
            metavar="<vnf-instance>",
            help=_("VNF instance ID to display"))
        return parser

    def take_action(self, parsed_args):
        client = self.app.client_manager.tackerclient
        obj = client.show_vnf_instance(parsed_args.vnf_instance)
        display_columns, columns = _get_columns(obj, action='show')
        data = utils.get_item_properties(
            sdk_utils.DictModel(obj),
            columns, mixed_case_fields=_mixed_case_fields,
            formatters={'instantiatedVnfInfo': format_columns.DictColumn})
        return (display_columns, data)


def instantiate_vnf_args2body(file_path):

    if file_path is not None and os.access(file_path, os.R_OK) is False:
        msg = _("File %s does not exist or user does not have read "
                "privileges to it")
        raise exceptions.InvalidInput(msg % file_path)

    try:
        with open(file_path) as f:
            body = json.load(f)
    except (IOError, ValueError) as ex:
        msg = _("Failed to load parameter file. Error: %s")
        raise exceptions.InvalidInput(msg % ex)

    if not body:
        raise exceptions.InvalidInput(_('The parameter file is empty'))

    return body


class InstantiateVnfLcm(command.Command):
    _description = _("Instantiate a VNF Instance")

    def get_parser(self, prog_name):
        parser = super(InstantiateVnfLcm, self).get_parser(prog_name)
        parser.add_argument(
            _VNF_INSTANCE,
            metavar="<vnf-instance>",
            help=_("VNF instance ID to instantiate"))
        parser.add_argument(
            'instantiation_request_file',
            metavar="<param-file>",
            help=_('Specify instantiate request parameters in a json file.'))

        return parser

    def take_action(self, parsed_args):
        client = self.app.client_manager.tackerclient
        result = client.instantiate_vnf_instance(
            parsed_args.vnf_instance, instantiate_vnf_args2body(
                parsed_args.instantiation_request_file))
        if not result:
            print((_('Instantiate request for VNF Instance %(id)s has been'
                     ' accepted.') % {'id': parsed_args.vnf_instance}))


class TerminateVnfLcm(command.Command):
    _description = _("Terminate a VNF instance")

    def get_parser(self, prog_name):
        parser = super(TerminateVnfLcm, self).get_parser(prog_name)
        parser.add_argument(
            _VNF_INSTANCE,
            metavar="<vnf-instance>",
            help=_("VNF instance ID to terminate"))
        parser.add_argument(
            "--termination-type",
            default='GRACEFUL',
            metavar="<termination-type>",
            choices=['GRACEFUL', 'FORCEFUL'],
            help=_("Termination type can be 'GRACEFUL' or 'FORCEFUL'. "
                   "Default is 'GRACEFUL'"))
        parser.add_argument(
            '--graceful-termination-timeout',
            metavar="<graceful-termination-timeout>",
            type=int,
            help=_('This attribute is only applicable in case of graceful '
                   'termination. It defines the time to wait for the VNF to be'
                   ' taken out of service before shutting down the VNF and '
                   'releasing the resources. The unit is seconds.'))
        parser.add_argument(
            '--D',
            action='store_true',
            default=False,
            help=_("Delete VNF Instance subsequently after it's termination"),
        )
        return parser

    def args2body(self, parsed_args):
        body = {}
        body['terminationType'] = parsed_args.termination_type

        if parsed_args.graceful_termination_timeout:
            if parsed_args.termination_type == 'FORCEFUL':
                exceptions.InvalidInput('--graceful-termination-timeout'
                                        ' argument is invalid for "FORCEFUL"'
                                        ' termination')
            body['gracefulTerminationTimeout'] = parsed_args.\
                graceful_termination_timeout

        return body

    def take_action(self, parsed_args):
        client = self.app.client_manager.tackerclient
        result = client.terminate_vnf_instance(parsed_args.vnf_instance,
                                               self.args2body(parsed_args))
        if not result:
            print(_("Terminate request for VNF Instance '%(id)s' has been"
                  " accepted.") % {'id': parsed_args.vnf_instance})
            if parsed_args.D:
                print(_("Waiting for vnf instance to be terminated before "
                      "deleting"))

                self._wait_until_vnf_is_terminated(
                    client, parsed_args.vnf_instance,
                    graceful_timeout=parsed_args.graceful_termination_timeout)

                result = client.delete_vnf_instance(parsed_args.vnf_instance)
                if not result:
                    print(_("VNF Instance '%(id)s' deleted successfully") %
                          {'id': parsed_args.vnf_instance})

    def _wait_until_vnf_is_terminated(self, client, vnf_instance_id,
                                      graceful_timeout=None):
        # wait until vnf instance 'instantiationState' is set to
        # 'NOT_INSTANTIATED'
        if graceful_timeout:
            # If graceful_termination_timeout is provided,
            # terminate vnf will start after this timeout period.
            # Hence, it should wait for extra time of 10 seconds
            # after this graceful_termination_timeout period.
            timeout = graceful_timeout + EXTRA_WAITING_TIME
        else:
            timeout = VNF_INSTANCE_TERMINATION_TIMEOUT

        start_time = int(time.time())
        while True:
            vnf_instance = client.show_vnf_instance(vnf_instance_id)
            if vnf_instance['instantiationState'] == 'NOT_INSTANTIATED':
                break

            if ((int(time.time()) - start_time) > timeout):
                msg = _("Couldn't verify vnf instance is terminated within "
                        "'%(timeout)s' seconds. Unable to delete vnf instance "
                        "%(id)s")
                raise exceptions.CommandError(msg % {'timeout': timeout,
                                              'id': vnf_instance_id})
            time.sleep(SLEEP_TIME)


class DeleteVnfLcm(command.Command):
    """Vnf lcm delete

    DeleteVnfLcm class supports bulk deletion of vnf instances, and error
    handling.
    """

    _description = _("Delete VNF Instance(s)")

    def get_parser(self, prog_name):
        parser = super(DeleteVnfLcm, self).get_parser(prog_name)
        parser.add_argument(
            'vnf_instances',
            metavar="<vnf-instance>",
            nargs="+",
            help=_("VNF instance ID(s) to delete"))
        return parser

    def take_action(self, parsed_args):
        error_count = 0
        client = self.app.client_manager.tackerclient
        vnf_instances = parsed_args.vnf_instances
        for vnf_instance in vnf_instances:
            try:
                client.delete_vnf_instance(vnf_instance)
            except Exception as e:
                error_count += 1
                LOG.error(_("Failed to delete vnf instance with "
                            "ID '%(vnf)s': %(e)s"),
                          {'vnf': vnf_instance, 'e': e})

        total = len(vnf_instances)
        if (error_count > 0):
            msg = (_("Failed to delete %(error_count)s of %(total)s "
                     "vnf instances.") % {'error_count': error_count,
                                          'total': total})
            raise exceptions.CommandError(msg)
        else:
            if total > 1:
                print(_('All specified vnf instances are deleted '
                        'successfully'))
            else:
                print(_("Vnf instance '%s' deleted "
                        "successfully") % vnf_instances[0])
