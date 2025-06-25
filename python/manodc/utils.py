""" General utility functions for MANODC service package """
import typing

import ncs


def get_single_node(path: str) -> typing.Union[str, int]:
    """Get a single node from the cdb."""
    with ncs.maapi.single_write_trans('root', "system") as trans:
        return trans.xpath_eval_expr(path, trace=None, path="")


def get_multi_node(path: str) -> typing.List[typing.Union[str, int]]:
    """Get multiple nodes from the cdb."""
    values = []
    with ncs.maapi.single_write_trans("root", "system") as trans:

        def helper_function(kp, _):
            values.append(ncs.maagic.get_node(trans, kp.dup()))

        trans.xpath_eval(path, helper_function, trace=None, path="")
    return values


def get_eor_from_site(site_name: str) -> typing.List[str]:
    """Get the EOR devices from the site."""
    inv_manager_path = f"inv:inventory-manager[inv:name='{site_name}']"
    devices_path = inv_manager_path + "/inv:device/inv:name[../inv:device-role='EOR']"
    eors = get_multi_node(devices_path)
    return [str(eor) for eor in eors]


def get_fabric_name(device_name: str) -> str:
    """Get the fabric name from the switch name"""
    inv_manager_path = "/inv:inventory-manager"
    device_path = inv_manager_path + f"/inv:device[inv:name='{device_name}']"
    site_path = device_path + "/../inv:name"
    site = get_single_node(site_path)
    return str(site)


def get_vrrpv3_ids(device_name: str) -> typing.List[int]:
    """Get the list of vrrpv3 id's from the switch name"""
    device = f"/devices/device[name= '{device_name}']/config"
    interface_vlan = device + "/nx:interface/Vlan/vrrpv3/vr"
    vrrpv3_ids = get_multi_node(interface_vlan)
    return [int(vrrpv3_id) for vrrpv3_id in vrrpv3_ids]


def get_vlan_ids(device_name: str) -> typing.List[int]:
    """Get the list of vlan id's from the switch name"""
    device = f"/devices/device[name= '{device_name}']/config"
    vlan = device + "/nx:vlan/vlan-list/id"
    vlan_ids = get_multi_node(vlan)
    return [int(vlan_id) for vlan_id in vlan_ids]
