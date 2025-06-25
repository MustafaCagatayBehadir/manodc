"""
This module contains classes and functions for the actions that are built for MANODC.
"""
import csv
import ipaddress
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Dict, List, Literal, Set, Tuple

import _ncs
import ncs
import requests  # type: ignore
from ncs.dp import Action

from . import utils

USER = 'root'

#pylint: disable-msg=too-many-arguments,too-many-arguments


def get_nested_parent(node, levels=1):
    """Retrieve a node by going up a specified number of _parent levels.

    Args:
        node: The starting node from which to traverse up the _parent chain.
        levels (int): Number of _parent levels to go up.

    Returns:
        The node at the specified parent level, or None if any _parent is missing.
    """
    for _ in range(levels):
        node = getattr(node, "_parent", None)
        if node is None:
            break
    return node


def add_states_to_component(component: ncs.application.PlanComponent, states: List[str]) -> None:
    """Add plan states to component."""
    for state in states:
        component.append_state(state)


def create_action_plan(func):
    """Create action plan data with."""

    @wraps(func)
    def set_plan_states(*args):
        """Create plan data for action node."""
        action_data, action_timestamp, action_username, switches, log = func(*args)
        action_data_component = ncs.application.PlanComponent(action_data, "self", "ncs:self")
        add_states_to_component(action_data_component, ["ncs:init", "manodc:configured", "ncs:ready"])
        action_str = f"{str(action_data)} {action_timestamp} {action_username}"
        log.info(f"Action {action_str} self component is created with states.")
        action_data_component.set_status("ncs:init", "reached")
        log.info(f"Action {action_str} self component ncs:init state is reached.")

        for switch in switches:
            sw_component = ncs.application.PlanComponent(action_data, switch, "manodc:switch")
            add_states_to_component(sw_component, ["ncs:init", "manodc:configured", "ncs:ready"])
            log.info(f"Action {action_str} {switch} component is created with states.")
            sw_component.set_status("ncs:init", "reached")
            log.info(f"Action {action_str} {switch} component ncs:init state is reached.")

        return action_data

    return set_plan_states


@dataclass(frozen=True)
class L2L3Info:
    """Represents Layer 2/3 information for a network configuration."""
    switch: str
    vlan: int
    description: str
    gw: str
    vrf: str
    gw_address: str
    subnet: str

    def __post_init__(self):
        if not isinstance(self.vlan, int):
            raise ValueError("vlan must be an integer")


@dataclass
class BdInfo:
    """Represents Bridge Domain information for a network configuration."""
    switch: str
    port: str
    service: str
    connected_host: str
    host_port: str
    port_mode: str
    vlans: str
    native_vlan: str
    storm_control: str


class ParseCsv(Action):
    """Action class for parsing CSV data and populating service configurations."""

    @Action.action
    def cb_action(self, uinfo, name, kp, action_input, action_output, trans):
        """
        Callback action for parsing CSV and populating service configurations.

        Args:
            uinfo: User info
            name: Action name
            kp: Keypath
            action_input: Input data
            action_output: Output data
            transaction: Transaction object
        """
        _ncs.dp.action_set_timeout(uinfo, 1800)
        self.log.info("Action ", name, "called by user ", uinfo.username)

        if action_input.data_source.string == "portal":
            bd_raw_data = self.pythonify_csv(source="portal", content=action_input.bd_data)
            l2l3_raw_data = self.pythonify_csv(source="portal", content=action_input.l2l3_data)
        else:
            bd_raw_data = self.pythonify_csv(source="csv", file_path=action_input.bd_data_csv_path)
            l2l3_raw_data = self.pythonify_csv(source="csv", file_path=action_input.l2l3_data_csv_path)

        all_bd_infos = self.process_bd(bd_raw_data)
        all_l2l3_infos = self.process_l2l3(l2l3_raw_data)

        with ncs.maapi.single_write_trans(USER, "system") as transaction:
            root = ncs.maagic.get_root(transaction)

            bd_service_instances = self.populate_service_with_bdinfo(root, all_bd_infos)
            self.populate_service_with_l2l3info(all_l2l3_infos, bd_service_instances)

            action_data = self.create_action_plan_data(root, self.get_switches_from_intent(bd_raw_data), uinfo.username)
            trace_id = action_input.trace_id or str(uuid.uuid1())
            action_data.trace_id = trace_id

            action_output.result = self.handle_transaction(transaction, action_input.dry_run, trace_id)

    def pythonify_csv(self, source: str, content: str = "", file_path: str = "") -> List[List[str]]:
        """Convert CSV content to a list of lists, skipping the header."""
        if source == "portal":
            reader = list(csv.reader(content.strip().split(' ')))
        else:
            with open(file_path, "r", encoding="utf-8") as file:
                reader = list(csv.reader(file))[1:]
        return reader

    def get_switches_from_intent(self, intent: List[List[str]]) -> Set[str]:
        """Get the switches from the intent."""
        switches = set()
        for switch, *_ in intent:  # Unpacking the line to directly access `switch`
            fabric_name = utils.get_fabric_name(switch)
            eors = utils.get_eor_from_site(fabric_name)
            switches.update([switch, *eors])  # Single update call
        return switches

    def process_bd(self, pyobj: List[List[str]]) -> List[BdInfo]:
        """Process Bridge Domain data and return a list of BdInfo objects."""
        return [BdInfo(*line) for line in pyobj]

    def populate_service_with_bdinfo(self, root: ncs.maagic.Root,
                                     all_bd_infos: List[BdInfo]) -> Dict[Tuple[str, int], ncs.maagic.ListElement]:
        """
        Populate service with Bridge Domain information.

        Args:
            root: Root of the cdb tree
            all_bd_infos: List of BdInfo objects

        Returns:
            Dictionary mapping (fabric_name, vlan) to bridge domain instances
        """
        all_bd_instances = {}
        for bd_info in all_bd_infos:
            fabric_name = utils.get_fabric_name(bd_info.switch)
            eor_info = utils.get_eor_from_site(fabric_name)

            service_vlans = self.get_bd_vlans(bd_info.vlans)
            native_vlan = None if bd_info.native_vlan == 'NA' else int(bd_info.native_vlan)

            for service_vlan in service_vlans:
                self.log.info(
                    f"Creating bridge domain for {fabric_name} service {bd_info.service} with VLAN {service_vlan}")
                bd_instance = root.manodc__bridge_domains.bridge_domain_vlan.create(fabric_name, bd_info.service,
                                                                                    service_vlan)
                all_bd_instances[(fabric_name, service_vlan)] = bd_instance

                for eor in eor_info:
                    bd_instance.switch.create(eor)

                tor_switch = bd_instance.switch.create(bd_info.switch)
                tor_port = tor_switch.port.create(bd_info.port)
                tor_port.connected_host = bd_info.connected_host
                tor_port.host_port = bd_info.host_port
                tor_port.mode = bd_info.port_mode.lower()

                if bd_info.port_mode.lower() == 'access':
                    tor_port.storm_control = bd_info.storm_control == 'Yes'

            if native_vlan is not None:
                bd_instance = root.manodc__bridge_domains.bridge_domain_vlan.create(fabric_name, bd_info.service,
                                                                                    native_vlan)
                all_bd_instances[(fabric_name, native_vlan)] = bd_instance

                for eor in eor_info:
                    bd_instance.switch.create(eor)

                tor_switch = bd_instance.switch.create(bd_info.switch)
                tor_port = tor_switch.port.create(bd_info.port)
                tor_port.connected_host = bd_info.connected_host
                tor_port.host_port = bd_info.host_port
                tor_port.mode = 'native'

        return all_bd_instances

    def get_bd_vlans(self, vlans: str) -> List[int]:
        """
            Parse VLAN ranges and return a list of individual VLAN numbers.

            Args:
                vlans: A string containing VLAN ranges

            Returns:
                A list of individual VLAN numbers
            """
        result: List[int] = []
        for vlan_range in vlans.replace('.', ',').split(','):
            if '-' in vlan_range:
                start, end = map(int, vlan_range.strip().split('-'))
                result.extend(range(start, end + 1))
            else:
                result.append(int(vlan_range.strip()))
        return result

    def process_l2l3(self, pyobj: List[List[str]]) -> List[L2L3Info]:
        """Process Layer 2/3 data and return a list of L2L3Info objects."""
        return [L2L3Info(line[0], int(line[1]), *line[2:]) for line in pyobj]

    def populate_service_with_l2l3info(self, all_l2l3_infos: List[L2L3Info],
                                       all_bd_instances: Dict[Tuple[str, int], ncs.maagic.ListElement]):
        """
        Populate service with Layer 2/3 information.

        Args:
            root: Root of the cdb tree
            all_l2l3_infos: List of L2L3Info objects
            all_bd_instances: Dictionary of bridge domain instances with keys of fabric name and vlan number
        """
        for l2l3_info in all_l2l3_infos:
            try:
                fabric_name = utils.get_fabric_name(l2l3_info.switch)
                bd_instance = all_bd_instances[(fabric_name, l2l3_info.vlan)]
                self.log.info(f"Creating Layer 3 configuration for {fabric_name} VLAN {l2l3_info.vlan}")
                bd_instance.description = l2l3_info.description
                if l2l3_info.gw == 'Yes':
                    layer3 = bd_instance.layer3.create()
                    layer3.vrf = l2l3_info.vrf
                    layer3.gateway = self.validate_gateway_address(f"{l2l3_info.gw_address}/{l2l3_info.subnet}")
            except KeyError as err:
                raise KeyError(f"bd_instance {l2l3_info.vlan} does not exist") from err

    def validate_gateway_address(self, gateway: str) -> str:
        """
        Validate the given gateway address.

        This function checks if the provided gateway address is valid and is neither
        a network address nor a broadcast address.

        Args:
            gateway (str): The gateway address in CIDR notation (e.g., "192.168.1.1/24")

        Returns:
            str: The validated gateway address

        Raises:
            ValueError: If the gateway address is invalid, a network address, or a broadcast address
        """
        try:
            network = ipaddress.ip_network(gateway, strict=False)
            ip = ipaddress.ip_address(gateway.split('/')[0])

            if ip == network.network_address:
                raise ValueError("Gateway address cannot be a network address.")
            if ip == network.broadcast_address:
                raise ValueError("Gateway address cannot be a broadcast address.")

            print(f"Valid gateway address: {gateway}")
            return gateway
        except ValueError as err:
            raise ValueError(f"Invalid gateway address: {err}") from err

    @create_action_plan
    def create_action_plan_data(self, root: ncs.maagic.Root, switches: Set[str],
                                username: str) -> Tuple[ncs.maagic.Node, str, str, Set[str], ncs.log.Log]:
        """Create action plan data for the action node."""
        utc_plus_3 = timezone(timedelta(hours=3))
        timestamp = datetime.now(utc_plus_3).strftime("%Y-%m-%dT%H:%M:%S+03:00")
        self.log.info(f"Creating action plan data for the action node parse-csv {timestamp} {username}.")
        action_data = root.manodc__manodc_actions.parse_csv_data.create(timestamp, username)
        return action_data, timestamp, username, switches, self.log

    def handle_transaction(self, trans: ncs.maapi.Transaction, dry_run: bool, trace_id: str) -> str:
        """
            Handle transaction based on commit flags.

            Args:
                trans: Transaction object
                dry_run: Boolean indicating if this is a dry run

            Returns:
                String containing the result of the transaction
            """
        params = trans.get_params()
        if dry_run:
            params.dry_run_native()
            dry_output = trans.apply_params(True, params)
            result: str = ""
            if "device" in dry_output:
                for device, output in dry_output["device"].items():
                    result += f"#### {device} dry run:\n {output}"
            return result

        params.trace_id(trace_id)
        trans.apply_params(True, params)
        self.log.info(f"Transaction is applied successfully with trace-id {trace_id}.")
        return "Services were populated with parsed data successfully."


class SendNotification(Action):
    """Action class to send notification to Odine."""

    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        """MefLegatoNotification action callback."""
        self.log.info("Action triggered: ", name)
        _ncs.dp.action_set_timeout(uinfo, 1800)
        self.log.info(f"Triggering kicker {input.kicker_id}, for path {input.path}, tid: {input.tid}")
        with ncs.maapi.single_read_trans(USER, "system", db=ncs.OPERATIONAL) as transaction:
            monitor_node = ncs.maagic.get_node(transaction, input.path)
            action_data = get_nested_parent(monitor_node, 5)
            components = action_data.plan.component
            if components["self"].state["ncs:ready"].status == "reached":
                payload = {
                    "status": "Completed",
                    "trace-id": action_data.trace_id,
                    "completed-devices": [component.name for component in components if component.name != "self"],
                    "failed-devices": []
                }
                self.log.info(f"Sending notification with payload: {payload}")
                self._send_payload_to_endpoint(payload,
                                               "http://spring-boot-app-service-odinemano.apps.i2iocp.turkcell.tgc",
                                               "/api/v1/bulk-compute-expansion/nso-response", 60)
            elif components["self"].state["ncs:ready"].status == "failed":
                payload = {
                    "status":
                    "Failed",
                    "trace-id":
                    action_data.trace_id,
                    "completed-devices": [
                        component.name for component in components
                        if component.name != "self" and component.state["ncs:ready"].status == "reached"
                    ],
                    "failed-devices": [
                        component.name for component in components
                        if component.name != "self" and component.state["ncs:ready"].status == "failed"
                    ]
                }
                self.log.info(f"Sending notification with payload: {payload}")
                self._send_payload_to_endpoint(payload,
                                               "http://spring-boot-app-service-odinemano.apps.i2iocp.turkcell.tgc",
                                               "/api/v1/bulk-compute-expansion/nso-response", 60)

    def _send_payload_to_endpoint(self, payload, base_url: str, endpoint: str, timeout: int):
        headers = {'Cache-Control': 'no-cache'}
        try:
            self.log.info(f"Sending NSO response to {endpoint}")
            self.log.info(f"Payload: {payload}")

            response = requests.post(url=f"{base_url}{endpoint}", json=payload, headers=headers, timeout=timeout)

            response.raise_for_status()

            self.log.info(f"Request successful. Status code: {response.status_code}")
            self.log.info(f"Response: {response.json()}")

        except requests.exceptions.HTTPError as e:
            self.log.error(f"HTTP error occurred: {str(e)}")
            self.log.error(f"Response status code: {response.status_code}")
            self.log.error(f"Response content: {response.text}")

        except Exception as e:
            self.log.error(f"Error sending the payload: {str(e)}")


class AllocateIds(Action):
    """Action class for allocating the used ID's for VLAN and VRRPV3 in the resource-manager"""

    @Action.action
    def cb_action(self, uinfo, name, kp, action_input, action_output, trans):
        """
        Callback action for manually allocating RM ID's.

        Args:
            uinfo: User info
            name: Action name
            kp: Keypath
            action_input: Input data
            action_output: Output data
            transaction: Transaction object
        """
        _ncs.dp.action_set_timeout(uinfo, 1800)
        self.log.info("cb_create: ", kp)

        with ncs.maapi.single_write_trans(USER, "system") as transaction:
            root = ncs.maagic.get_root(transaction)
            site = root.inv__inventory_manager[action_input.site]
            vrrpv3_id_pool = site.site_configs.resource_pools.vrrpv3_id_pool
            vlan_id_pool = site.site_configs.resource_pools.vlan_id_pool
            self.log.info(vlan_id_pool)
            for eor in utils.get_eor_from_site(site.name):
                self.log.info(eor)
                for vrrpv3_id in utils.get_vrrpv3_ids(eor):
                    self.allocate_resource(site, vrrpv3_id_pool, "VRRPV3", vrrpv3_id, USER)
                    self.log.info(vrrpv3_id)

                for vlan_id in utils.get_vlan_ids(eor):
                    self.allocate_resource(site, vlan_id_pool, "VLAN", vlan_id, USER)
                    self.log.info(vlan_id)
            transaction.apply()

    def allocate_resource(self, site: ncs.maagic.ListElement, pool_name: str, resource_type: Literal["VLAN", "VRRPV3"],
                          resource_id: int, user: str):
        """ Allocate ID's from resource manager depending on the resource type """
        template = ncs.template.Template(site)
        tvars = ncs.template.Variables()
        tvars.add("POOL_NAME", pool_name)
        tvars.add("ALLOCATION_NAME", f"MANUAL_{resource_type}_{resource_id}")
        tvars.add("USERNAME", user)
        tvars.add("ID", resource_id)
        template.apply('manodc-nx-allocate-resources', tvars)
