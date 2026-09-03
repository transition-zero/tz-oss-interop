"""Fixture builders, one module per framework interop reads or writes.

Each module holds a builder that assembles a source document component by
component and serialises it once, plus the readers its assertions use to read
one back. The matching pytest-bdd vocabulary lives in ``interop_testing.steps``;
the builders themselves are plain Python and can be driven directly.
"""
