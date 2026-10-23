"""NARIT Aura migration runner — EPIC 1 (schema + index cure)."""
import os
import sys
import time
from pathlib import Path
from neo4j import GraphDatabase


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        sys.exit(f"FATAL: {path} not found — run from repo root")
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run(driver, db, label, cypher, expect=None):
    print(f"\n[{label}]")
    with driver.session(database=db) as s:
        result = s.run(cypher)
        rows = [r.data() for r in result]
    for r in rows:
        print("  ", r)
    if expect:
        for key, want in expect.items():
            got = rows[0].get(key) if rows else None
            if got != want:
                sys.exit(f"FAIL [{label}] — {key}={got!r}, expected {want!r}")
    return rows


def main():
    load_env()
    uri  = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USERNAME")
    pwd  = os.environ.get("NEO4J_PASSWORD")
    db   = os.environ.get("NEO4J_DATABASE", "neo4j")
    if not all([uri, user, pwd]):
        sys.exit("FATAL: NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD missing in .env")

    print(f"connecting to {uri} (db={db})")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        driver.verify_connectivity()
        print("  connectivity OK")

        # ---- B0 pre-flight ----
        run(driver, db, "B0 pre-flight",
            "MATCH (s:Section) WHERE s.code IS NULL OR s.number IS NULL "
            "RETURN count(s) AS bad_nodes",
            expect={"bad_nodes": 0})

        # ---- B1 backfill ----
        run(driver, db, "B1 backfill uid/statute_role/is_legacy",
            """
            MATCH (s:Section)
            SET s.uid = s.code + '_' + toString(s.number),
                s.statute_role = CASE
                    WHEN s.code IN ['IPC','BNS'] THEN 'Substantive_Offence'
                    WHEN s.code IN ['CrPC','BNSS'] THEN 'Criminal_Procedural'
                    WHEN s.code IN ['IEA','BSA']   THEN 'Evidence'
                    ELSE 'Civil_Special'
                END,
                s.is_legacy = s.code IN ['IPC','CrPC','IEA']
            RETURN count(s) AS updated
            """)

        # ---- B2 constraint ----
        run(driver, db, "B2 uniqueness constraint",
            "CREATE CONSTRAINT section_uid_unique IF NOT EXISTS "
            "FOR (s:Section) REQUIRE s.uid IS UNIQUE "
            "RETURN 'created' AS status")

        # ---- B3 edge metadata ----
        run(driver, db, "B3 tag MAPS_TO edges",
            """
            MATCH (a:Section)-[m:MAPS_TO]->(b:Section)
            SET m.mapping_type = COALESCE(m.mapping_type, 'Direct'),
                m.change_notes = COALESCE(m.change_notes, '')
            RETURN count(m) AS tagged
            """)

        # ---- B4 seed search_aliases ----
        run(driver, db, "B4 seed search_aliases",
            "MATCH (s:Section) WHERE s.search_aliases IS NULL "
            "SET s.search_aliases = '' "
            "RETURN count(s) AS seeded")

        # ---- B5 index rebuild (separate transactions) ----
        run(driver, db, "B5a drop old index",
            "DROP INDEX sectionSearch IF EXISTS", )
        run(driver, db, "B5b create fulltext index (3 fields)",
            """
            CREATE FULLTEXT INDEX sectionSearch IF NOT EXISTS
            FOR (s:Section) ON EACH [s.title, s.search_aliases, s.text]
            OPTIONS { indexConfig: { `fulltext.analyzer`: 'english' } }
            """)

        # ---- C1 / C2 ----
        run(driver, db, "C1 counts",
            "MATCH (s:Section) "
            "RETURN count(s) AS total, count(s.uid) AS with_uid, "
            "count(s.search_aliases) AS with_aliases",
            expect={"total": 1031, "with_uid": 1031, "with_aliases": 1031})
        run(driver, db, "C2 edge metadata",
            "MATCH (:Section)-[m:MAPS_TO]->(:Section) "
            "RETURN count(m) AS maps, "
            "sum(CASE WHEN m.mapping_type IS NULL THEN 1 ELSE 0 END) AS missing_type",
            expect={"maps": 564, "missing_type": 0})

        # ---- C3 index state: poll for ONLINE ----
        print("\n[C3 index state]")
        for attempt in range(1, 13):
            with driver.session(database=db) as s:
                row = s.run(
                    "SHOW INDEXES YIELD name, properties, state "
                    "WHERE name = 'sectionSearch' "
                    "RETURN properties, state"
                ).single()
            if row is None:
                sys.exit("FAIL [C3] — sectionSearch index not found")
            props = list(row["properties"])
            state = row["state"]
            print(f"   attempt {attempt}: props={props} state={state}")
            if props == ["title", "search_aliases", "text"] and state == "ONLINE":
                print("\nALL CHECKS PASSED")
                return
            if state == "POPULATING":
                time.sleep(5)
                continue
            if state == "FAILED":
                sys.exit("FAIL [C3] — index state FAILED, check Aura logs")
            time.sleep(2)
        sys.exit("FAIL [C3] — index did not reach ONLINE within 60s")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
