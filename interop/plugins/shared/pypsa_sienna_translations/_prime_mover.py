from __future__ import annotations

import polars as pl

from interop.plugins.shared.sienna_constants import SiennaPrimeMovers


def enrich_prime_mover(
    table: pl.DataFrame,
    carrier_col: str,
    dest_col: str,
    prime_mover_map: dict[str, SiennaPrimeMovers],
) -> pl.DataFrame:
    """Add the prime_mover enrichment column by mapping each row's carrier via the user mapping.

    Dropped by finalise(); exists only so the prime_mover_type translation is a single-column
    expr. An empty mapping (no carriers declared) leaves the carrier value in place for the
    empty table that necessarily accompanies it.
    """
    if not prime_mover_map:
        return table.with_columns(pl.col(carrier_col).alias(dest_col))
    values = {carrier: str(prime_mover) for carrier, prime_mover in prime_mover_map.items()}
    return table.with_columns(pl.col(carrier_col).replace(values).alias(dest_col))
