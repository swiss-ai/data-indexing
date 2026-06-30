#!/usr/bin/env python3
"""
Merge final_dataset_8B and final_dataset_70B into a single parquet for indexing.

All conversations from both datasets are included. True text duplicates (identical
text from both models) are deduplicated downstream at ES index time via SHA256(_id).
id field: "{shard_filename}:{row_within_shard}" — e.g. "alignment-merged-0003.parquet:12741".

Text: system prompt (if non-empty) + user prompt + all reference-completion responses,
      concatenated with role markers.
Output schema: text (string), id (string).

Output: output_dir/alignment-merged-{shard:04d}.parquet
        Each shard holds ~SHARD_SIZE rows (default 50 000).

Usage
-----
python3 preprocess_alignment.py \\
    --dir-8b  /capstor/.../alignment_datasets_v1/final_dataset_8B \\
    --dir-70b /capstor/.../alignment_datasets_v1/final_dataset_70B \\
    --output-dir /capstor/.../alignment_merged/
"""

import argparse
import glob
import logging
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SHARD_SIZE = 50_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


# ── Text builder ─────────────────────────────────────────────────────────────

def _build_text(row: dict) -> str:
    """Build conversation text with User: / Model: role labels.

    Each conversation has one user prompt and multiple reference-completion
    responses from different models.  We label them so readers (and search)
    can distinguish the question from the answers.
    """
    parts = []

    prompt_content = (row.get("initial_prompt") or {}).get("content", "").strip()
    if prompt_content:
        parts.append(f"User: {prompt_content}")

    branches = row.get("conversation_branches") or []
    for b in branches:
        if b.get("is_reference_completion") is True:
            for msg in b.get("messages") or []:
                if msg.get("role") != "assistant":
                    continue
                for part in msg.get("parts") or []:
                    content = (part.get("content") or "").strip()
                    if content:
                        parts.append(f"Model: {content}")

    return "\n\n".join(parts)


# ── Arrow stream reader ───────────────────────────────────────────────────────

def _iter_arrow_dir(base_dir: str):
    files = sorted(glob.glob(f"{base_dir}/data-*.arrow"))
    if not files:
        raise FileNotFoundError(f"No data-*.arrow files in {base_dir}")
    logger.info(f"  {len(files)} Arrow shards in {base_dir}")
    for fp in files:
        with open(fp, "rb") as f:
            reader = pa.ipc.open_stream(f)
            while True:
                try:
                    batch = reader.read_next_batch()
                    for i in range(batch.num_rows):
                        yield {col: batch.column(col)[i].as_py()
                               for col in batch.schema.names}
                except StopIteration:
                    break


# ── Parquet writer ────────────────────────────────────────────────────────────

SCHEMA = pa.schema([
    pa.field("text", pa.string()),
    pa.field("id",   pa.string()),
])


class ShardWriter:
    def __init__(self, output_dir: Path, shard_size: int):
        self.output_dir  = output_dir
        self.shard_size  = shard_size
        self.shard_idx   = 0
        self._buf: list  = []
        self.total_written = 0

    def add(self, record: dict):
        self._buf.append(record)
        if len(self._buf) >= self.shard_size:
            self._flush()

    def _flush(self):
        if not self._buf:
            return
        table = pa.table(
            {
                "text": [r["text"] for r in self._buf],
                "id":   [r["id"]   for r in self._buf],
            },
            schema=SCHEMA,
        )
        out_path = self.output_dir / f"alignment-merged-{self.shard_idx:04d}.parquet"
        pq.write_table(table, str(out_path), compression="snappy")
        logger.info(f"  Wrote shard {self.shard_idx}: {len(self._buf):,} rows → {out_path.name}")
        self.total_written += len(self._buf)
        self.shard_idx += 1
        self._buf = []

    def close(self):
        self._flush()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir-8b",     required=True,
                        help="Path to final_dataset_8B directory")
    parser.add_argument("--dir-70b",    required=True,
                        help="Path to final_dataset_70B directory")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to write output parquet shards")
    parser.add_argument("--shard-size", type=int, default=SHARD_SIZE,
                        help=f"Rows per output shard (default: {SHARD_SIZE})")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    writer             = ShardWriter(output_dir, args.shard_size)
    skipped_empty      = 0
    total_8b           = total_70b = 0
    total_rows_written = 0

    def _make_id(n: int) -> str:
        shard_idx    = n // args.shard_size
        row_in_shard = n % args.shard_size
        return f"alignment-merged-{shard_idx:04d}.parquet:{row_in_shard}"

    # ── Pass 1: 8B ────────────────────────────────────────────────────────────
    logger.info("Pass 1: reading final_dataset_8B ...")
    for row in _iter_arrow_dir(args.dir_8b):
        text = _build_text(row)
        if not text:
            skipped_empty += 1
            continue
        writer.add({"text": text, "id": _make_id(total_rows_written)})
        total_8b += 1
        total_rows_written += 1

    logger.info(f"  8B: {total_8b:,} conversations written, {skipped_empty} empty skipped")

    # ── Pass 2: 70B ───────────────────────────────────────────────────────────
    logger.info("Pass 2: reading final_dataset_70B ...")
    skipped_empty_70b = 0
    for row in _iter_arrow_dir(args.dir_70b):
        text = _build_text(row)
        if not text:
            skipped_empty_70b += 1
            continue
        writer.add({"text": text, "id": _make_id(total_rows_written)})
        total_70b += 1
        total_rows_written += 1

    writer.close()

    logger.info("=" * 60)
    logger.info(f"  From 8B:             {total_8b:,}")
    logger.info(f"  From 70B:            {total_70b:,}")
    logger.info(f"  Skipped (empty):     {skipped_empty + skipped_empty_70b:,}")
    logger.info(f"Total written to parquet: {writer.total_written:,}")
    logger.info(f"Output: {output_dir}  ({writer.shard_idx} shards)")


if __name__ == "__main__":
    main()
