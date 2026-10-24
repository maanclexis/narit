"""Fetch bge-small-en-v1.5 ONNX artifacts from HuggingFace into models/embedder/.

Uses only stdlib (urllib.request) so no extra deps beyond what the embedder itself needs.
Idempotent: skips files already present with non-zero size unless --force is passed.

Model: Xenova/bge-small-en-v1.5 (ONNX int8 port). 384-dim, CLS pooling, L2 normalized.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

REPO = "Xenova/bge-small-en-v1.5"
BASE = f"https://huggingface.co/{REPO}/resolve/main"

# (remote_path, local_filename)
FILES = [
    ("onnx/model_quantized.onnx", "model_quantized.onnx"),
    ("tokenizer.json", "tokenizer.json"),
    ("tokenizer_config.json", "tokenizer_config.json"),
    ("config.json", "config.json"),
    ("special_tokens_map.json", "special_tokens_map.json"),
]


def _download(url: str, dest: Path) -> None:
    print(f"  -> {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            read += len(chunk)
            if total:
                pct = 100 * read // total
                print(f"     {read}/{total} bytes ({pct}%)", end="\r")
    tmp.replace(dest)
    print(f"     saved {dest.name} ({dest.stat().st_size} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="models/embedder", help="output directory")
    ap.add_argument("--force", action="store_true", help="redownload even if file exists")
    args = ap.parse_args()

    dest = Path(args.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Destination: {dest}")

    failed = False
    for remote, local in FILES:
        target = dest / local
        if target.exists() and target.stat().st_size > 0 and not args.force:
            print(f"  skip {local} (exists, {target.stat().st_size} bytes)")
            continue
        try:
            _download(f"{BASE}/{remote}", target)
        except Exception as exc:
            print(f"  FAIL {remote}: {exc}", file=sys.stderr)
            failed = True

    if failed:
        print("\nSome files failed. Re-run to retry missing ones.", file=sys.stderr)
        return 1

    print("\nDone. Files in", dest)
    for f in sorted(dest.iterdir()):
        print(f"  {f.name:30s} {f.stat().st_size:>10d} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
