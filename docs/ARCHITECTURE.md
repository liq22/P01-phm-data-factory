# Architecture

```text
Apache IoTDB meta rows -> MetadataCatalog ----+
                                                +-> PHMDataRepository -> CLI/MCP Agent
Apache IoTDB signals ---> SignalStore --------+

legacy metadata.xlsx/CSV + HDF5 ---------------> one-time IoTDB import
```

The repository returns NumPy arrays. `AgentDataTools` is an anti-corruption
layer that returns JSON-safe bounded results and only accepts exact structured
filters. This prevents Agent runtime requirements from entering training code.
