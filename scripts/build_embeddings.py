"""Embed every Section (title+text) once and write the vector onto the node.

v3.c item 3.4 - index-time half. Query-time blending lives in api/hybrid.py.

  python scripts/build_embeddings.py            # dry run: embed 5 samples, print dims, no write
  python scripts/build_embeddings.py --write    # embed all sections, SET s.embedding, create index
  python scripts/build_embeddings.py --write --force   # re-embed sections that already have one

Idempotent: sections that already carry a 384-dim embedding are skipped unless --force.
The vector index is created with IF NOT EXISTS, safe to re-run.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

# Make api.embedder importable when run from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import embedder  # noqa: E402

EMBED_DIM = embedder.EMBED_DIM
BATCH = 16
INDEX_NAME = "sectionEmbedding"


def _driver():
    load_dotenv()
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
    )


def _db():
    return os.getenv("NEO4J_DATABASE")


def _passage(title: str, text: str) -> str:
    title = (title or "").strip()
    text = (text or "").strip()
    return (title + "\n" + text).strip()


def _create_index(session) -> None:
    session.run(
        f"""
        CREATE VECTOR INDEX {INDEX_NAME} IF NOT EXISTS
        FOR (s:Section) ON (s.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {EMBED_DIM},
            `vector.similarity_function`: 'cosine'
        }}}}
        """
    )
    print(f"  vector index '{INDEX_NAME}' ensured ({EMBED_DIM}-dim, cosine)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write embeddings + create index")
    ap.add_argument("--force", action="store_true", help="re-embed sections that already have a vector")
    ap.add_argument("--limit", type=int, default=0, help="process only first N sections (debug)")
    args = ap.parse_args()

    if not embedder.is_available():
        print("embedder unavailable (model files or deps missing). Aborting.", file=sys.stderr)
        print("Run: python scripts/fetch_embedder.py", file=sys.stderr)
        return 2

    driver = _driver()
    try:
        with driver.session(database=_db()) as session:
            total = session.run("MATCH (s:Section) RETURN count(s) AS c").single()["c"]
            print(f"Sections in graph: {total}")

            if args.write and not args.force:
                have = session.run(
                    "MATCH (s:Section) WHERE s.embedding IS NOT NULL RETURN count(s) AS c"
                ).single()["c"]
                print(f"Already embedded: {have}")

            where = "" if args.force else "WHERE s.embedding IS NULL"
            limit = f"LIMIT {args.limit}" if args.limit > 0 else ""
            rows = list(
                session.run(
                    f"""
                    MATCH (s:Section)
                    {where}
                    RETURN s.uid AS uid, s.title AS title, s.text AS text
                    ORDER BY s.uid
                    {limit}
                    """
                )
            )
            print(f"To embed this run: {len(rows)}")

            if not args.write:
                for r in rows[:5]:
                    vec = embedder.embed_passages([_passage(r["title"], r["text"])])
                    if vec is None:
                        print("  embed failed on sample; aborting")
                        return 1
                    print(f"  sample {r['uid']}: dim={len(vec[0])}")
                print("\nDry run complete. Re-run with --write to persist.")
                return 0

            written = 0
            for i in range(0, len(rows), BATCH):
                chunk = rows[i : i + BATCH]
                passages = [_passage(r["title"], r["text"]) for r in chunk]
                vecs = embedder.embed_passages(passages)
                if vecs is None:
                    print(f"  embed failed at batch offset {i}; aborting", file=sys.stderr)
                    return 1
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (s:Section {uid: row.uid})
                    SET s.embedding = row.vec
                    """,
                    rows=[{"uid": r["uid"], "vec": v} for r, v in zip(chunk, vecs)],
                )
                written += len(chunk)
                print(f"  embedded {written}/{len(rows)}", end="\r")
            print()

            _create_index(session)

            final = session.run(
                "MATCH (s:Section) WHERE s.embedding IS NOT NULL RETURN count(s) AS c"
            ).single()["c"]
            print(f"Sections with embedding: {final}")
    finally:
        driver.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
