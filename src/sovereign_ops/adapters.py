"""Interfaces only. Implementations and acquisition belong to G1."""

from collections.abc import Iterator
from pathlib import Path
from typing import Literal, Protocol

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DataQualityReport,
    DatasetId,
    TelemetryPoint,
)


class DomainAdapter(Protocol):
    @property
    def dataset_id(self) -> DatasetId: ...

    def inspect(self, root: Path, manifest: AcquisitionManifest) -> DataQualityReport:
        """Verify source bytes, rights, identity, and schema before reporting quality."""
        ...

    def iter_points(self, root: Path, manifest: AcquisitionManifest) -> Iterator[TelemetryPoint]:
        """Reject unverified bytes and unsupported permissions before emitting any point."""
        ...


class ESAAdapter(DomainAdapter, Protocol):
    @property
    def dataset_id(self) -> Literal["ESA-AD-v2"]: ...


class EDPAdapter(DomainAdapter, Protocol):
    @property
    def dataset_id(self) -> Literal["EDP-SCADA-v2"]: ...
