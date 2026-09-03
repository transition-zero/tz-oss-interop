"""NetCDF format detection for reading networks through a byte stream.

The C ``netcdf4`` engine only reads from a filesystem path, so reading a network from
a ``FilesystemPort`` stream requires an engine that accepts a file object. No single
such engine reads both formats PyPSA emits: classic NETCDF3 (``scipy``) and HDF5-based
NETCDF4 (``h5netcdf``). The leading magic bytes distinguish them, so the engine is
picked per stream from its signature.
"""

from __future__ import annotations

from typing import IO

# Classic NetCDF (versions 1 and 2) streams begin "CDF"; HDF5-based NetCDF4 begins
# with the HDF5 signature. Anything else is not a network file we can read.
_CLASSIC_NETCDF_MAGIC = b"CDF"
_HDF5_MAGIC = b"\x89HDF"


def netcdf_engine(stream: IO[bytes]) -> str:
    """Return the xarray engine for ``stream``, restoring its position to the start."""
    signature = stream.read(4)
    stream.seek(0)
    if signature.startswith(_CLASSIC_NETCDF_MAGIC):
        return "scipy"
    if signature.startswith(_HDF5_MAGIC):
        return "h5netcdf"
    raise ValueError(
        f"unrecognised netCDF signature {signature!r}; expected classic NetCDF or HDF5"
    )
