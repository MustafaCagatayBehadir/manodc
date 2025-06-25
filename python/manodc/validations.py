"""Gateway validation callback."""

import ipaddress
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import Tuple, Union

import ncs
import ncs.keypath
from ncs.dp import ValidationError, ValidationPoint

from . import utils

USER = "admin"


class GatewayValidationCallback(ValidationPoint):
    """Gateway validation class."""

    @contextmanager
    def get_root(self, tctx):
        """Context manager for Maapi root."""
        _maapi = ncs.maapi.Maapi()
        try:
            trans = _maapi.attach(tctx)
            root = ncs.maagic.get_root(trans)
            yield root
        finally:
            _maapi.detach(tctx)

    def get_nx_ip_route_data(self, root: ncs.maagic.Root, device: str) -> Union[ncs.maagic.List, str]:
        """Retrieve IP route data from the NX-OS device, fallback to CLI if not available."""
        cli_input = root.ncs__devices.device[device].live_status.nx_stats__exec.any.get_input()
        cli_input.args = ["show ip route vrf all | xml"]
        output = root.ncs__devices.device[device].live_status.nx_stats__exec.any(cli_input)
        return output.result

    def is_usable_host(self, root: ncs.maagic.Root, _keypath: str) -> Tuple[bool, str]:
        """Check if the IP address is a usable host address."""
        try:
            ip_with_subnet = ncs.maagic.cd(root, _keypath)
            network_address = ipaddress.IPv4Network(ip_with_subnet, strict=False)[0]
            interface_address = ipaddress.IPv4Interface(ip_with_subnet).ip
            broadcast_address = ipaddress.IPv4Network(ip_with_subnet, strict=False).broadcast_address

            if interface_address == network_address:
                return False, f"{interface_address} is the network address."
            if interface_address == broadcast_address:
                return False, f"{interface_address} is the broadcast address."
            return True, f"{interface_address} is a usable host address."
        except ValueError as err:
            return False, f"Invalid IP/subnet: {err}"

    def is_subnet_available(self, root: ncs.maagic.Root, _keypath: str, site_name: str, log) -> Tuple[bool, str]:
        """Check if the subnet is available."""

        def remove_namespace(tag):
            if "}" in tag:
                return tag.split("}", 1)[1]
            return tag

        site = root.inv__inventory_manager[site_name].site_configs

        if site.validations.subnet_validation.string == "disable":
            return True, "Subnet validation is disabled."

        device = utils.get_eor_from_site(site_name)[0]
        log.info(f"Checking subnet for site {site_name} device {device}")
        ip_route = self.get_nx_ip_route_data(root, device)
        xml_root = ET.fromstring(ip_route.strip().strip("]]>]]>"))
        ipprefixes = [elem.text for elem in xml_root.iter() if remove_namespace(elem.tag) == "ipprefix"]

        networks = {ipaddress.IPv4Network(prefix) for prefix in ipprefixes}
        gateway_network = ipaddress.IPv4Interface(ncs.maagic.cd(root, _keypath)).network

        if gateway_network in networks:
            log.error(f"Subnet {gateway_network} is already in use.")
            return False, f"Subnet {gateway_network} is already in use."

        for network in networks:
            if gateway_network.supernet_of(network):
                log.error(f"Subnet {gateway_network} overlaps with {network}.")
                return False, f"Subnet {gateway_network} overlaps with {network}."

        return True, f"Subnet {gateway_network} is available."

    @ValidationPoint.validate
    def cb_validate(self, tctx, keypath, value, validationpoint):
        """Validate the gateway address."""
        self.log.info(f"Validating: {keypath} = {value}")

        with self.get_root(tctx) as root:
            is_host_ip, validation_msg = self.is_usable_host(root, str(keypath))
            if not is_host_ip:
                self.log.error(f"Validation failed: {validation_msg}")
                raise ValidationError(validation_msg)
            self.log.info(f"Validation is succeeded for gateway is usable host check: {validation_msg}")

            site_name = str(keypath[2][0])
            is_subnet_available, validation_msg = self.is_subnet_available(root, str(keypath), site_name, self.log)
            if not is_subnet_available:
                self.log.error(f"Validation failed: {validation_msg}")
                raise ValidationError(validation_msg)
            self.log.info(f"Validation is succeeded for subnet availability check: {validation_msg}")
