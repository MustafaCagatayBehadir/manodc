"""Service callback handler for the bridge-domain service."""

import ipaddress
from typing import List, Tuple

import ncs
from resource_manager.id_allocator import id_read, id_request

USER = "admin"


def get_node_modified_keypath(node: ncs.maagic.ListElement) -> str:
    """Get modified version of the keypath for allocation names."""
    keypath = getattr(node, "_path")
    modified_keypath = keypath.split(":")[1].replace("/", "_").replace("{", "_").replace("}", "").replace(" ", "_")
    return modified_keypath


def read_allocated_id(root: ncs.maagic.Root, pool: str, allocation_name: str, log: ncs.log.Log) -> int:
    """Read allocated ID from specific pool."""
    try:
        allocated_id = id_read(USER, root, pool, allocation_name)
        if not allocated_id.isdigit():
            raise ValueError(allocated_id)
        log.info(f"Pool: {pool} - Allocation: {allocation_name} - Id: {allocated_id}")
    except LookupError as err:
        raise LookupError(f"\n{pool} - {allocation_name} - failed with:\n\n{err}\n") from err
    return allocated_id


def allocate_vlan_id(root: ncs.maagic.Root, bdvlan: ncs.maagic.ListElement, pool: str, xpath: str, log: ncs.log.Log):
    """Allocate fabric vlan id."""
    vlan_id = bdvlan.vlan
    alloc_name = get_node_modified_keypath(bdvlan)
    id_request(bdvlan, xpath, USER, pool, alloc_name, False, vlan_id, alloc_sync=True, root=root)
    log.info(f"Pool {pool} vlan-id is allocated.")
    vlan_id = read_allocated_id(root, pool, alloc_name, log)
    log.info(f"Pool {pool} vlan-id {vlan_id} is read.")
    return vlan_id


def allocate_vrrpv3_id(root: ncs.maagic.Root, bdvlan: ncs.maagic.ListElement, pool: str, xpath: str, log: ncs.log.Log):
    """Allocate fabric vrrpv3 id."""
    alloc_name = get_node_modified_keypath(bdvlan)
    id_request(bdvlan, xpath, USER, pool, alloc_name, False, -1, alloc_sync=True, root=root)
    log.info(f"Pool {pool} vrrpv3-id is allocated.")
    vrrpv3_id = read_allocated_id(root, pool, alloc_name, log)
    log.info(f"Pool {pool} vrrpv3-id {vrrpv3_id} is read.")
    return vrrpv3_id


def is_switch_eor(vlan: ncs.maagic.ListElement, device: str) -> bool:
    """Check if the switch is an EoR switch."""
    switch_type = vlan.switch[device].switch_type
    return switch_type == "eor"


def is_eor_primary(root: ncs.maagic.Root, location: str, hall: str, fabric: str, device: str) -> bool:
    """Check if the switch is an EoR primary switch."""
    role = root.manodc__dc_sites.dc_site[location, hall, fabric].eor[device].role
    return role == "primary"


def get_primary_address(gateway: str) -> str:
    """Get the primary address of the EoR switch."""
    vip = ipaddress.IPv4Interface(gateway)
    prefixlen = gateway.split("/")[1]
    return str(vip.ip + 1) + "/" + prefixlen


def get_secondary_address(gateway: str) -> str:
    """Get the secondary address of the EoR switch."""
    vip = ipaddress.IPv4Interface(gateway)
    prefixlen = gateway.split("/")[1]
    return str(vip.ip + 2) + "/" + prefixlen


class BdVlanServiceCallback(ncs.application.NanoService):
    """Service callback handler for the vlan service."""

    @ncs.application.NanoService.create
    def cb_nano_create(self, tctx, root, service, plan, component, state, proplist, compproplist):
        """Bridge-Domain Vlan service nano create callback."""
        self.log.info("Nano create(state=", state, ")")

        if state == "manodc:id-allocated":
            proplist = self.allocate_ids(root, service, [])
            self.log.info(f"proplist: {proplist}")

        elif state == "manodc:vlan-configured":
            device = str(component[1])
            self.configure_bdvlan_switch(root, service, proplist, device)

        return proplist

    def allocate_ids(self, root: ncs.maagic.Root, bdvlan: ncs.maagic.ListElement,
                     _proplist: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Allocate resource-manager ids for the bridge-domain vlan service."""
        site_name = bdvlan.site
        location, hall, fabric = site_name.split("-")
        bd_name = bdvlan.name
        vlan_id = bdvlan.vlan
        site = root.manodc__dc_sites.dc_site[location, hall, fabric]
        vlan_pool = site.manodc__resource_pools.vlan_id_pool
        vrrpv3_pool = site.manodc__resource_pools.vrrpv3_id_pool
        bdvlan_xpath = f"/bridge-domains/bridge-domain-vlan[site='{site}'][name='{bd_name}'][vlan='{vlan_id}']"
        allocated_vlan_id = allocate_vlan_id(root, bdvlan, vlan_pool, bdvlan_xpath, self.log)
        _proplist.append(("vlan_id", allocated_vlan_id))
        if bdvlan.layer3.exists():
            allocated_vrrpv3_id = allocate_vrrpv3_id(root, bdvlan, vrrpv3_pool, bdvlan_xpath, self.log)
            _proplist.append(("vrrpv3_id", allocated_vrrpv3_id))
        else:
            _proplist.append(("vrrpv3_id", "-1"))
        return _proplist

    def configure_bdvlan_switch(self, root: ncs.maagic.Root, bdvlan: ncs.maagic.ListElement,
                                proplist: List[Tuple[str, str]], device: str) -> None:
        """Configure vlan-switch list."""
        vrrpv3_id = proplist[1][1]
        site_name = bdvlan.site
        location, hall, fabric = site_name.split("-")
        template = ncs.template.Template(bdvlan)
        tvars = ncs.template.Variables()
        tvars.add("SWITCH", device)
        if is_switch_eor(bdvlan, device):
            gateway = bdvlan.layer3.gateway
            is_primary = is_eor_primary(root, location, hall, fabric, device)
            address = get_primary_address(gateway) if is_primary else get_secondary_address(gateway)
            vrrpv3_priority = 110 if is_primary else 100
            tvars.add("VRRPV3_ID", vrrpv3_id)
            tvars.add("ADDRESS", address)
            tvars.add("VRRPV3_PRIORITY", vrrpv3_priority)
        else:
            tvars.add("VRRPV3_ID", vrrpv3_id)
            tvars.add("ADDRESS", "")
            tvars.add("VRRPV3_PRIORITY", -1)
        self.log.info(f"Configuring vlan-switch for {device}...")
        template.apply("manodc-vlan-switch", tvars)
        self.log.info(f"Vlan-switch for {device} configured.")


class BdVlanSwitchServiceCallback(ncs.application.NanoService):
    """Service callback handler for the vlan switch service."""

    @ncs.application.NanoService.create
    def cb_nano_create(self, tctx, root, service, plan, component, state, proplist, compproplist):
        """Vlan switch service nano create callback."""
        self.log.info("Nano create(state=", state, ")")

        if state == "manodc:vlan-switch-configured":
            self.configure_bdvlan(service)

    def configure_bdvlan(self, bdvlan: ncs.maagic.ListElement) -> None:
        """Configure vlan-id."""
        template = ncs.template.Template(bdvlan)
        tvars = ncs.template.Variables()
        bd_name = bdvlan.name
        vlan_id = bdvlan.vlan
        device = bdvlan.switch
        self.log.info(f"Configuring bridge-domain {bd_name} vlan {vlan_id} for {device}...")
        template.apply("manodc-xe-vlan", tvars)
        self.log.info(f"Bridge-domain {bd_name} vlan {vlan_id} for {device} configured.")
