"""Pytest shared fixtures."""

import json
from types import SimpleNamespace
from unittest import mock

import pytest


class NetboxObject(SimpleNamespace):
    """Simple object to represent a pynetbox API response with a save() method and dict representation."""

    def __iter__(self):
        """Make the object convertable to dict."""
        # The JSON passage is needed to recursively convert all the NetboxObject instances to dict
        return iter(
            json.loads(json.dumps(self, default=lambda x: {i: j for i, j in x.__dict__.items() if i != "save"})).items()
        )


def _base_netbox_obj(name, additional_properties):
    """Return a simple object to represent a response from Netbox API."""
    dict_obj = {
        "name": name,
        "id": 1,
        "asset_tag": "ASSET1234",
        "status": {"value": "active", "label": "Active"},
        "primary_ip4": {
            "id": 1,
            "family": 4,
            "address": "10.0.0.1/22",
            "dns_name": f"{name}.example.com",
        },
        "primary_ip6": {
            "id": 1,
            "family": 6,
            "address": "2620:0:861:103:10::1/64",
            "dns_name": f"{name}.example.com",
            "assigned_object_type": "dcim.interface",
        },
        "role": {
            "id": 1,
            "name": "Server",
            "slug": "server",
        },
        "device_type": {
            "manufacturer": {
                "slug": "dell",
            },
        },
    }
    dict_obj["primary_ip"] = dict_obj["primary_ip6"]
    dict_obj["primary_ip"]["assigned_object"] = {
        "id": 1,
        "connected_endpoints": [{"untagged_vlan": {"name": "test_vlan"}}],
        "mac_address": "11:22:33:44:55:66",
        "type": {"value": "10gbase-x-sfpp"},
    }
    dict_obj.update(additional_properties)

    def custom_hook(decoded_dict):
        """Custom hook for JSON load to convert a dict to an object with a save() attribute."""
        decoded_obj = NetboxObject(**decoded_dict)
        decoded_obj.save = mock.MagicMock(return_value=True)  # pylint: disable=attribute-defined-outside-init
        return decoded_obj

    obj = json.loads(json.dumps(dict_obj), object_hook=custom_hook)
    obj.status.__str__ = lambda: dict_obj["status"]["label"]

    return obj


@pytest.fixture()
def netbox_host():
    """Return a mocked Netbox physical device."""
    return _base_netbox_obj("physical", {"rack": {"id": 1, "name": "rack1"}, "cluster": None})


@pytest.fixture()
def netbox_virtual_machine():
    """Return a mocked Netbox virtual machine."""
    return _base_netbox_obj("virtual", {"cluster": {"id": 1, "name": "testcluster"}})
