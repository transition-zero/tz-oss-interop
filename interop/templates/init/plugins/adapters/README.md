# Project-local outbound adapters

Drop a `.py` file here defining a class that inherits an outbound port
Protocol (e.g. `FilesystemPort` from `interop.ports.outbound.filesystem`).
It will be discovered alongside the built-in adapters when you run
interop from this project's root. See `docs/developer_documentation/extending.md` in the
interop repository for the protocol shapes and how an adapter gets
bound to a port.
