"""Optional TSCG (tool-schema compression) integration for SkillReducer."""

from skillreducer.tscg.compress import (
    TscgError,
    TscgResult,
    compress_tools,
    node_available,
    tscg_dependency_installed,
    write_tscg_outputs,
)
from skillreducer.tscg.manifest import (
    find_existing_manifest,
    load_tools_json,
    normalize_tools,
    tools_from_scripts,
    write_mcp_manifest,
)

__all__ = [
    "TscgError",
    "TscgResult",
    "compress_tools",
    "find_existing_manifest",
    "load_tools_json",
    "node_available",
    "normalize_tools",
    "tools_from_scripts",
    "tscg_dependency_installed",
    "write_mcp_manifest",
    "write_tscg_outputs",
]
