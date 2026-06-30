#!/usr/bin/env python3
"""
Preprocess SFT mixture parquet files for indexing into Elasticsearch.

Downloads from HuggingFace or reads a local directory of parquet shards.
Builds a flat text string from each conversation's messages:
  - System turn included if non-empty (prefix "System: ")
  - User turns included as "User: {text}"
  - Assistant turns included as "Assistant: {text}"
  - Developer role (tool/function context) is skipped
  - Multi-turn conversations are joined with double newlines

No deduplication — all rows are included. True text duplicates are handled
downstream by ES (SHA256 _id).

Output schema:
  text  string
  id    string   ("{shard_filename}:{row_within_shard}", e.g. "sft-merged-0003.parquet:12741")

Output files: output_dir/sft-merged-{shard:04d}.parquet

Usage
-----
python3 preprocess_sft.py \\
    --input-dir /path/to/sft-parquet-shards/ \\
    --output-dir /path/to/output/
"""

import argparse
import logging
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SHARD_SIZE = 50_000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Text builder ──────────────────────────────────────────────────────────────

def _extract_text(messages) -> str:
    """Build flat conversation text from the messages list.

    User text lives in content.parts[].text; assistant text in content.blocks[].text.
    System is included when non-empty. Developer role (tool context) is skipped.
    """
    parts = []
    for m in (messages or []):
        if not m:
            continue
        role = (m.get("role") or "").lower()
        if role == "developer":
            continue  # tool/function context, not conversational text

        content = m.get("content") or {}
        text = ""

        # user messages use content.parts[].text
        msg_parts = content.get("parts") or []
        if msg_parts:
            text = " ".join(
                p.get("text", "") for p in msg_parts if p and p.get("text")
            )

        # assistant messages use content.blocks[].text
        if not text:
            blocks = content.get("blocks") or []
            if blocks:
                text = " ".join(
                    b.get("text", "") for b in blocks if b and b.get("text")
                )

        # fallback to content.text
        if not text:
            text = content.get("text") or ""

        text = text.strip()
        if not text:
            continue

        if role == "system":
            parts.append(f"System: {text}")
        elif role == "user":
            parts.append(f"User: {text}")
        elif role == "assistant":
            parts.append(f"Assistant: {text}")

    return "\n\n".join(parts)


# ── Parquet writer ────────────────────────────────────────────────────────────

SCHEMA = pa.schema([
    pa.field("text", pa.string()),
    pa.field("id",   pa.string()),
])


class ShardWriter:
    def __init__(self, output_dir: Path, shard_size: int):
        self.output_dir    = output_dir
        self.shard_size    = shard_size
        self.shard_idx     = 0
        self._buf: list    = []
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
        out_path = self.output_dir / f"sft-merged-{self.shard_idx:04d}.parquet"
        pq.write_table(table, str(out_path), compression="snappy")
        logger.info(f"  Wrote shard {self.shard_idx}: {len(self._buf):,} rows → {out_path.name}")
        self.total_written += len(self._buf)
        self.shard_idx += 1
        self._buf = []

    def close(self):
        self._flush()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input-dir",  required=True,
                        help="Directory containing SFT parquet shards (train-*.parquet)")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to write sft-merged-NNNN.parquet shards")
    parser.add_argument("--shard-size", type=int, default=SHARD_SIZE,
                        help=f"Rows per output shard (default: {SHARD_SIZE})")
    args = parser.parse_args()

    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.rglob("*.parquet"))
    if not files:
        logger.error(f"No parquet files found in {input_dir}")
        sys.exit(1)
    logger.info(f"Found {len(files)} parquet shard(s) in {input_dir}")

    writer             = ShardWriter(output_dir, args.shard_size)
    skipped_empty      = 0
    total_rows         = 0
    total_rows_written = 0

    for fp in files:
        logger.info(f"Processing {fp.name} ...")
        pf = pq.ParquetFile(str(fp))
        for batch in pf.iter_batches(batch_size=5_000):
            rows = batch.to_pydict()
            n = len(rows.get("conversation_id", []))
            for i in range(n):
                total_rows += 1
                msgs = rows["messages"][i] or []
                text = _extract_text(msgs)
                if not text:
                    skipped_empty += 1
                    continue

                shard_idx    = total_rows_written // args.shard_size
                row_in_shard = total_rows_written % args.shard_size
                doc_id = f"sft-merged-{shard_idx:04d}.parquet:{row_in_shard}"
                writer.add({"text": text, "id": doc_id})
                total_rows_written += 1

    writer.close()

    logger.info("=" * 60)
    logger.info(f"Total rows read:         {total_rows:,}")
    logger.info(f"Skipped (empty text):    {skipped_empty:,}")
    logger.info(f"Written to parquet:      {writer.total_written:,}  ({writer.shard_idx} shards)")
    logger.info(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
