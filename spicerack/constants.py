"""Constants module."""

PUPPET_CA_PATH: str = "/etc/ssl/certs/Puppet_Internal_CA.pem"
"""The path to the Puppet Signing CA cert"""

KEYHOLDER_SOCK: str = "/run/keyholder/proxy.sock"
"""The path to the keyholder agent sock file used for cumin remote commands"""
