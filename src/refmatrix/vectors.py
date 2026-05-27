"""Lance-backed vector store for dense ANN retrieval.

Layout on disk:

    <root>/.refmatrix/vectors/<partition>/<kind>.lance/

One Lance dataset per (partition, kind). Each dataset has a stable
schema:

    id:         int64        -- entity id; uniqued on upsert
    vector:     fixed_size_list<float32, dim>
    updated_at: timestamp[us, UTC]

ANN search is L2-distance based for now. Lance's `nearest` API
returns rows sorted by `_distance` ascending; we surface that as a
distance score (lower = better). Callers that want similarity should
convert via `1.0 / (1.0 + d)` or `exp(-d)` at fuse time.

Soft dependency: importing this module requires the [dense] extra
(pylance + numpy). Daemon / Store code only imports it lazily so
SQLite-only installs don't pay the import cost.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pyarrow as pa


def _arrow_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.int64(), nullable=False),
            pa.field(
                "vector",
                pa.list_(pa.field("item", pa.float32()), dim),
                nullable=False,
            ),
            pa.field("updated_at", pa.timestamp("us", tz="UTC"), nullable=False),
        ]
    )


class LanceVectorStore:
    """Thin wrapper around per-(partition, kind) Lance datasets.

    Datasets are created lazily on first `upsert_vectors` for a given
    kind. `ann_search` returns `[(entity_id, distance), ...]`.
    Datasets that don't exist contribute no hits silently — callers
    can query any kind without pre-checking existence.
    """

    def __init__(self, root: Path, partition: str, dim: int):
        self.root = Path(root).resolve()
        self.partition = partition
        self.dim = dim
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / partition).mkdir(parents=True, exist_ok=True)

    # --- paths ---------------------------------------------------------
    def _dataset_path(self, kind: str) -> Path:
        return self.root / self.partition / f"{kind}.lance"

    # --- write ---------------------------------------------------------
    def upsert_vectors(
        self,
        entity_ids: Sequence[int],
        vectors: np.ndarray,
        *,
        kind: str,
    ) -> None:
        import lance

        if len(entity_ids) == 0:
            return
        vectors = np.asarray(vectors, dtype="float32")
        if vectors.ndim != 2 or vectors.shape[1] != self.dim:
            raise ValueError(
                f"vectors must be (N, {self.dim}); got {vectors.shape}"
            )
        if vectors.shape[0] != len(entity_ids):
            raise ValueError(
                f"len(entity_ids)={len(entity_ids)} != vectors.shape[0]"
                f"={vectors.shape[0]}"
            )

        ts_now = np.datetime64("now", "us")
        # numpy datetime64 is tz-naive; cast through a tz-naive Arrow
        # array, then to tz=UTC so it matches the dataset schema.
        now_naive = pa.array(
            [ts_now] * len(entity_ids), type=pa.timestamp("us")
        )
        now = now_naive.cast(pa.timestamp("us", tz="UTC"))
        # Build a fixed-size-list-of-float32 column from the (N, dim)
        # ndarray. Convert per-row to a Python list of floats so Arrow
        # accepts the FixedSizeList type without ambiguity.
        vec_col = pa.array(
            [v.tolist() for v in vectors],
            type=pa.list_(pa.field("item", pa.float32()), self.dim),
        )
        batch = pa.table(
            {
                "id": pa.array(list(entity_ids), type=pa.int64()),
                "vector": vec_col,
                "updated_at": now,
            },
            schema=_arrow_schema(self.dim),
        )

        path = self._dataset_path(kind)
        if path.exists():
            ds = lance.dataset(str(path))
            # MERGE INSERT upserts by id. Lance's merge_insert API uses
            # a builder pattern: match on id, update matched, insert
            # unmatched. Net effect: per-id last-write-wins.
            ds.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(batch)
        else:
            lance.write_dataset(batch, str(path), mode="create")

    def drop_for(self, entity_ids: Iterable[int], *, kind: str) -> int:
        import lance

        ids = list(entity_ids)
        if not ids:
            return 0
        path = self._dataset_path(kind)
        if not path.exists():
            return 0
        ds = lance.dataset(str(path))
        # Lance's delete takes a SQL WHERE clause.
        in_list = ",".join(str(int(i)) for i in ids)
        ds.delete(f"id IN ({in_list})")
        return len(ids)

    # --- read ----------------------------------------------------------
    def ann_search(
        self,
        query_vec: np.ndarray,
        k: int,
        *,
        kinds: Sequence[str] | None = None,
        candidate_ids: Sequence[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Per-kind ANN search merged into one top-k.

        Args:
            query_vec: float32 vector of length `self.dim`.
            k: how many hits to return after merging across kinds.
            kinds: limit search to these kinds; None auto-discovers
                every .lance dataset under this partition.
            candidate_ids: optional pre-filter — restrict the
                scanner to rows whose `id` is in this set. Lets
                callers narrow the ANN candidate pool with a
                bitmap-derived id list (the hybrid retrieval
                pattern). Empty list → no hits.
        """
        import lance

        if kinds is None:
            # Auto-discover by listing existing .lance dirs.
            base = self.root / self.partition
            if not base.exists():
                return []
            kinds = [
                p.name.removesuffix(".lance")
                for p in base.iterdir()
                if p.suffix == ".lance"
            ]
        query = np.asarray(query_vec, dtype="float32").reshape(-1)
        if query.shape[0] != self.dim:
            raise ValueError(
                f"query_vec dim={query.shape[0]} != store dim={self.dim}"
            )

        # Build the SQL IN filter once if a candidate set was supplied.
        # Empty candidate set is unambiguous: caller asked for "search
        # within nothing", return nothing.
        filter_expr: str | None = None
        if candidate_ids is not None:
            ids = list(candidate_ids)
            if not ids:
                return []
            in_list = ",".join(str(int(i)) for i in ids)
            filter_expr = f"id IN ({in_list})"

        all_hits: list[tuple[int, float]] = []
        for kind in kinds:
            path = self._dataset_path(kind)
            if not path.exists():
                continue
            ds = lance.dataset(str(path))
            # Include `_distance` in the requested columns explicitly:
            # Lance 0.20+ deprecated the auto-projection that previously
            # tacked it on when missing.
            kwargs: dict = dict(
                nearest={"column": "vector", "q": query, "k": k},
                columns=["id", "_distance"],
            )
            if filter_expr is not None:
                kwargs["filter"] = filter_expr
            tbl = ds.to_table(**kwargs)
            ids = tbl.column("id").to_pylist()
            # `_distance` is the virtual column Lance attaches for nearest.
            dists = tbl.column("_distance").to_pylist()
            for eid, dist in zip(ids, dists):
                all_hits.append((int(eid), float(dist)))

        # Merge per-kind top-k into a single top-k by distance ascending.
        all_hits.sort(key=lambda r: r[1])
        return all_hits[:k]
