"""Append-only stores for feature matrices, unvalidated predictions, and run records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .contracts import (
    ProductionFeatureMatrix,
    ProductionPredictionPublication,
    ProductionRunResult,
)


class ProductionFeatureMatrixStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, matrix: ProductionFeatureMatrix) -> Path:
        digest = _digest(matrix.matrix_id, "market-feature-matrix:")
        return _publish(
            self._root / "feature-matrices" / digest / "matrix.json",
            matrix.model_dump(mode="json"),
        )

    def load(self, matrix_id: str) -> ProductionFeatureMatrix:
        digest = _digest(matrix_id, "market-feature-matrix:")
        matrix = ProductionFeatureMatrix.model_validate_json(
            (self._root / "feature-matrices" / digest / "matrix.json").read_text(encoding="utf-8")
        )
        if matrix.matrix_id != matrix_id:
            raise ValueError("生产特征矩阵路径与身份不一致")
        return matrix


class ProductionPredictionStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, publication: ProductionPredictionPublication) -> Path:
        digest = _digest(
            publication.publication_id,
            "market-prediction-publication:",
        )
        return _publish(
            self._root / "predictions" / digest / "publication.json",
            publication.model_dump(mode="json"),
        )

    def load(self, publication_id: str) -> ProductionPredictionPublication:
        digest = _digest(publication_id, "market-prediction-publication:")
        publication = ProductionPredictionPublication.model_validate_json(
            (self._root / "predictions" / digest / "publication.json").read_text(encoding="utf-8")
        )
        if publication.publication_id != publication_id:
            raise ValueError("预测发布路径与身份不一致")
        return publication


class ProductionRunStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, result: ProductionRunResult) -> Path:
        digest = _digest(result.run_id, "market-model-run:")
        family = _family_segment(result.model_family)
        path = _publish(
            self._root / "runs" / family / f"{digest}.json",
            result.model_dump(mode="json"),
        )
        request_digest = _digest(result.request_id, "sha256:")
        _publish(
            self._root / "requests" / f"{request_digest}.json",
            {
                "request_id": result.request_id,
                "run_id": result.run_id,
                "model_family": result.model_family,
            },
        )
        return path

    def for_request(self, request_id: str) -> ProductionRunResult:
        request_digest = _digest(request_id, "sha256:")
        pointer = json.loads(
            (self._root / "requests" / f"{request_digest}.json").read_text(encoding="utf-8")
        )
        if not isinstance(pointer, dict) or pointer.get("request_id") != request_id:
            raise ValueError("生产训练请求身份不一致")
        run_id = str(pointer.get("run_id", ""))
        family = str(pointer.get("model_family", ""))
        digest = _digest(run_id, "market-model-run:")
        result = ProductionRunResult.model_validate_json(
            (self._root / "runs" / _family_segment(family) / f"{digest}.json").read_text(
                encoding="utf-8"
            )
        )
        if result.run_id != run_id or result.request_id != request_id:
            raise ValueError("生产训练运行引用不一致")
        return result


def _publish(path: Path, value: object) -> Path:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"同一不可变身份内容冲突：{path.name}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _digest(identity: str, prefix: str) -> str:
    digest = identity.removeprefix(prefix)
    if not identity.startswith(prefix) or len(digest) != 64:
        raise ValueError(f"非法内容身份：{identity}")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"非法内容身份：{identity}")
    return digest


def _family_segment(value: str) -> str:
    if value and value not in {".", ".."} and not any(character in value for character in "/\\"):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"unsupported-{digest}"


__all__ = [
    "ProductionFeatureMatrixStore",
    "ProductionPredictionStore",
    "ProductionRunStore",
]
