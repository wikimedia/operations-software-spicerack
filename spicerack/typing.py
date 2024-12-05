"""Custom Spicerack type hints."""

from collections.abc import Sequence
from typing import TypeVar

from cumin import NodeSet

TypeHosts = TypeVar("TypeHosts", Sequence[str], NodeSet)
"""Custom type for hosts, can be a :py:class:`ClusterShell.NodeSet.NodeSet` or any sequence of :py:class:`str`."""
