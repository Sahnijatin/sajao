"""Adapters turn a source's data into `Listing`s. Feeds add one module each."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from sajao_catalog.adapters import curated
from sajao_catalog.model import Listing

ADAPTERS: dict[str, Callable[[Path], Iterator[Listing]]] = {"curated": curated.listings}
