"""Every year that a `ByYear` field of the sidecar keys.

A Sienna system states no year. The sidecar keys a yearly value by its year, so the years of
those keys are the years of the model. A record that holds a list of further records, such as
the operating modes of a technology, keys yearly values too, so the walk goes into it.
"""

from __future__ import annotations

import functools
from typing import get_args, get_origin

from pydantic import BaseModel

from interop.core.extension_records import ByYear, ExtensionRecord, FlagByYear
from interop.core.extensions import ExtensionReader, Extensions

_YEAR_KEYED = (ByYear, FlagByYear)


def list_sidecar_years(reader: ExtensionReader) -> list[int]:
    """The years of the whole sidecar, in order. Reading them marks no record as read."""
    years: set[int] = set()
    for model in _list_record_models():
        for record in reader.read(model).list_records():
            years |= _list_record_years(record)
    return sorted(years)


def _list_record_models() -> tuple[type[ExtensionRecord], ...]:
    return tuple(_get_item_model(field.annotation) for field in Extensions.model_fields.values())


def _get_item_model(annotation: object) -> type[ExtensionRecord]:
    model = get_args(annotation)[0]
    if not (isinstance(model, type) and issubclass(model, ExtensionRecord)):
        raise TypeError(f"the sidecar field {annotation} does not hold extension records")
    return model


def _list_record_years(record: BaseModel) -> set[int]:
    model = type(record)
    years = {year for name in _list_year_fields(model) for year in (getattr(record, name) or {})}
    held = (value for name in _list_nested_fields(model) for value in (getattr(record, name) or ()))
    return years.union(*(_list_record_years(value) for value in held))


@functools.cache
def _list_year_fields(model: type[BaseModel]) -> tuple[str, ...]:
    return tuple(
        name for name, field in model.model_fields.items() if _is_year_keyed(field.annotation)
    )


@functools.cache
def _list_nested_fields(model: type[BaseModel]) -> tuple[str, ...]:
    """The name of each field that holds a list of further records, which keys years of its own."""
    return tuple(
        name
        for name, field in model.model_fields.items()
        if _find_nested_model(field.annotation) is not None
    )


def _is_year_keyed(annotation: object) -> bool:
    return annotation in _YEAR_KEYED or any(arg in _YEAR_KEYED for arg in get_args(annotation))


def _find_nested_model(annotation: object) -> type[BaseModel] | None:
    """The record model of a field that holds a list of further records; None for any other."""
    for candidate in (annotation, *get_args(annotation)):
        if get_origin(candidate) is list:
            held = get_args(candidate)[0]
            return held if isinstance(held, type) and issubclass(held, BaseModel) else None
    return None
