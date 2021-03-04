"""Custom Spicerack type hints."""
from typing import Sequence, TypeVar

from cumin import NodeSet

TypeHosts = TypeVar("TypeHosts", Sequence[str], NodeSet)
""":py:class:`typing.TypeVar` for hosts, can be a :py:class:`ClusterShell.NodeSet.NodeSet` or any sequence of
:py:class:`str`."""
