"""Read and verify exact immutable DataSnapshot inputs without using a current pointer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb

from astramind_mini.contracts import DataSnapshot
from astramind_mini.data.public import DatasetManifest

from ...application.identity import research_hash


class ProductionInputError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class VerifiedSnapshot:
    snapshot: DataSnapshot
    manifests: dict[str, DatasetManifest]
    parquet_paths: dict[str, tuple[Path, ...]]


class VerifiedSnapshotReader:
    """Verify exact identities plus WP-0057 physical integrity for consumed datasets."""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def load(
        self,
        snapshot_id: str,
        *,
        required_datasets: tuple[str, ...],
    ) -> VerifiedSnapshot:
        try:
            snapshot = self._load_snapshot(snapshot_id)
            references = {item.dataset_name: item for item in snapshot.datasets}
            if len(references) != len(snapshot.datasets):
                raise ProductionInputError("data_snapshot_duplicate_dataset")
            manifests = {
                name: self._load_manifest(
                    name,
                    reference.dataset_version,
                    reference.content_hash,
                )
                for name, reference in references.items()
            }
            missing = tuple(sorted(set(required_datasets) - manifests.keys()))
            if missing:
                raise ProductionInputError("missing_dataset:" + ",".join(missing))
            artifact_sets = {
                name: self._verify_artifact_bytes(manifest) for name, manifest in manifests.items()
            }
            paths = {
                name: self._verify_parquet_artifacts(
                    manifests[name],
                    artifact_sets[name],
                )
                for name in required_datasets
            }
        except FileNotFoundError as error:
            raise ProductionInputError("immutable_snapshot_artifact_missing") from error
        except duckdb.Error as error:
            raise ProductionInputError("immutable_snapshot_parquet_invalid") from error
        return VerifiedSnapshot(snapshot=snapshot, manifests=manifests, parquet_paths=paths)

    def _load_snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = _digest(snapshot_id, "snapshot:sha256:")
        snapshot = DataSnapshot.model_validate_json(
            (self._root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
        )
        identity = {
            "as_of": snapshot.as_of,
            "datasets": [item.model_dump(mode="json") for item in snapshot.datasets],
            "known_gaps": snapshot.known_gaps,
            "code_identity": snapshot.code_identity,
        }
        if snapshot.snapshot_id != snapshot_id or snapshot_id != "snapshot:" + research_hash(
            identity
        ):
            raise ProductionInputError("data_snapshot_identity_invalid")
        return snapshot

    def _load_manifest(
        self,
        name: str,
        version: str,
        expected_content_hash: str,
    ) -> DatasetManifest:
        digest = _digest(version, "sha256:")
        segment = _safe_segment(name)
        manifest = DatasetManifest.model_validate_json(
            (self._root / "datasets" / segment / digest / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        if (
            manifest.dataset_name != name
            or manifest.dataset_version != version
            or manifest.content_hash != expected_content_hash
        ):
            raise ProductionInputError(f"dataset_reference_invalid:{name}")
        identity: dict[str, object] = {
            "dataset_name": manifest.dataset_name,
            "schema_version": manifest.schema_version,
            "provider": manifest.provider,
            "source_endpoint": manifest.source_endpoint,
            "request_identity": manifest.request_identity,
            "retrieved_at": manifest.retrieved_at,
            "market_timezone": manifest.market_timezone,
            "date_range": manifest.date_range,
            "universe": manifest.universe,
            "primary_key": manifest.primary_key,
            "availability_rule": manifest.availability_rule,
            "units": manifest.units,
            "content_hash": manifest.content_hash,
            "row_count": manifest.row_count,
            "known_gaps": manifest.known_gaps,
            "critical_gaps": manifest.critical_gaps,
            "artifact_paths": manifest.artifact_paths,
            "publish_status": manifest.publish_status,
        }
        if manifest.provider_lineage:
            identity["provider_lineage"] = [
                item.model_dump(mode="json") for item in manifest.provider_lineage
            ]
        if research_hash(identity) != manifest.dataset_version:
            raise ProductionInputError(f"dataset_manifest_identity_invalid:{name}")
        if manifest.critical_gaps:
            raise ProductionInputError(f"dataset_critical_gap:{name}")
        return manifest

    def _verify_artifact_bytes(self, manifest: DatasetManifest) -> dict[str, Path]:
        directory = (
            self._root
            / "datasets"
            / _safe_segment(manifest.dataset_name)
            / _digest(manifest.dataset_version, "sha256:")
        )
        artifacts: dict[str, Path] = {}
        for name in manifest.artifact_paths:
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ProductionInputError(
                    f"immutable_artifact_path_invalid:{manifest.dataset_name}"
                )
            path = directory / relative
            if not path.is_file():
                raise ProductionInputError(f"immutable_artifact_missing:{manifest.dataset_name}")
            if path.stat().st_nlink > 1:
                raise ProductionInputError(
                    f"immutable_artifact_shared_inode:{manifest.dataset_name}"
                )
            artifacts[name] = path
        hashes = {name: _file_hash(path) for name, path in sorted(artifacts.items())}
        if research_hash(hashes) != manifest.content_hash:
            raise ProductionInputError(f"immutable_artifact_hash_invalid:{manifest.dataset_name}")
        return artifacts

    def _verify_parquet_artifacts(
        self,
        manifest: DatasetManifest,
        artifacts: dict[str, Path],
    ) -> tuple[Path, ...]:
        parquet_paths = tuple(
            path for name, path in sorted(artifacts.items()) if name.endswith(".parquet")
        )
        if not parquet_paths:
            raise ProductionInputError(f"parquet_artifact_missing:{manifest.dataset_name}")
        self._verify_parquet(manifest, parquet_paths)
        return parquet_paths

    def _verify_parquet(
        self,
        manifest: DatasetManifest,
        paths: tuple[Path, ...],
    ) -> None:
        parquet = [str(path) for path in paths]
        with duckdb.connect(":memory:") as connection:
            columns = {
                str(row[0])
                for row in connection.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true)",
                    [parquet],
                ).fetchall()
            }
            if missing := tuple(key for key in manifest.primary_key if key not in columns):
                raise ProductionInputError(
                    f"parquet_primary_key_missing:{manifest.dataset_name}:{','.join(missing)}"
                )
            keys = ", ".join(_quote(key) for key in manifest.primary_key)
            row = connection.execute(
                f"SELECT count(*), count(DISTINCT ({keys})) "
                "FROM read_parquet(?, union_by_name=true)",
                [parquet],
            ).fetchone()
            assert row is not None
            if int(row[0]) != manifest.row_count or int(row[1]) != manifest.row_count:
                raise ProductionInputError(f"parquet_row_identity_invalid:{manifest.dataset_name}")
            date_key = next(
                (
                    key
                    for key in manifest.primary_key
                    if key in {"trade_date", "calendar_date", "market_date", "nav_date"}
                ),
                None,
            )
            if date_key is not None and manifest.row_count:
                observed = connection.execute(
                    f"SELECT min({_quote(date_key)}), max({_quote(date_key)}) "
                    "FROM read_parquet(?, union_by_name=true)",
                    [parquet],
                ).fetchone()
                assert observed is not None
                if (observed[0], observed[1]) != manifest.date_range:
                    raise ProductionInputError(
                        f"parquet_date_range_invalid:{manifest.dataset_name}"
                    )


def _digest(identity: str, prefix: str) -> str:
    digest = identity.removeprefix(prefix)
    if not identity.startswith(prefix) or len(digest) != 64:
        raise ProductionInputError("content_identity_invalid")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ProductionInputError("content_identity_invalid")
    return digest


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."} or any(character in value for character in "/\\"):
        raise ProductionInputError("dataset_name_invalid")
    return value


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


__all__ = [
    "ProductionInputError",
    "VerifiedSnapshot",
    "VerifiedSnapshotReader",
]
