"""Constants module."""

CORE_DATACENTERS = ("eqiad", "codfw")
"""tuple: list of core datacenters."""

PUPPET_CA_PATH = "/etc/ssl/certs/Puppet_Internal_CA.pem"
"""str: the path to the Puppet Signing CA cert"""

KEYHOLDER_SOCK = "/run/keyholder/proxy.sock"
"""str: The path to the keyholder agent sock file used for cumin remote commands"""
