# plugins/adapters

Outbound port implementations (file IO, model loaders, etc.) live here. Each adapter class must:

- inherit from the Port Protocol it implements (e.g. `class S3Filesystem(FilesystemPort):`),
- declare `name: ClassVar[str] = "..."` — the lookup key used in the registry, and
- declare `port: ClassVar[type] = FilesystemPort` — the Port it serves, bucketed by `Registry.adapters[port]`.

Adapter names are unique per Port. Two adapters serving different Ports may share a name without colliding.
