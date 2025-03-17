"""Constants module."""

WMF_CA_BUNDLE_PATH: str = "/etc/ssl/certs/wmf-ca-certificates.crt"
"""The path to the internal WMF CA certificates bundle, includes the old Puppet CA."""

KEYHOLDER_SOCK: str = "/run/keyholder/proxy.sock"
"""The path to the keyholder agent sock file used for cumin remote commands."""
