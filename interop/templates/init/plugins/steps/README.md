# Project-local steps

Drop a `.py` file here defining a class that inherits the
`TranslationStep` Protocol from `interop.core.pipeline`. It will be
discovered when you run `interop translate` from this project's root.
Reference the step by its `name` attribute in a pipeline YAML. See
`docs/developer_documentation/extending.md` in the interop repository for the protocol shape
and a worked example.
