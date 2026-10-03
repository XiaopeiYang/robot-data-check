"""All checks that the CLI, MCP server and pipeline run, in report order.

Add a check module here once it is implemented and has a fault-injection test.
"""

from ..registry import Check
from . import frame_index


def _as_check(module) -> Check:
    return Check(name=module.NAME, version=module.VERSION, run=module.run)


ALL_CHECKS: list[Check] = [
    _as_check(frame_index),
]
