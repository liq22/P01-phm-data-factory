# Agent contract

Use `AgentDataTools` or MCP. Do not give an Agent arbitrary Pandas query
strings, unrestricted IoTDB SQL, or raw HDF5 handles.

Sequence: summary -> structured search -> metadata -> statistics -> bounded
window -> validation. IoTDB import is intentionally not exposed as an Agent
tool because it mutates storage.
