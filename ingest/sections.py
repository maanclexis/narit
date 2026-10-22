"""Seed statutes and load sections into Neo4j.

Usage:  python -m ingest.sections
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ["NEO4J_URI"]
AUTH = (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
DB = os.environ.get("NEO4J_DATABASE", "neo4j")

ONTOLOGY = Path(__file__).resolve().parent.parent / "ontology" / "narit_ontology.json"

# ── Seed statutes ─────────────────────────────────────────────────────
SEED_STATUTES = [
    {"id": "NDPS_ACT_1985", "name": "NDPS_Act_1985",
     "full_title": "Narcotic Drugs and Psychotropic Substances Act, 1985",
     "year": 1985, "jurisdiction": "India", "status": "active"},
    {"id": "BNS_2023", "name": "BNS_2023",
     "full_title": "Bharatiya Nyaya Sanhita, 2023",
     "year": 2023, "jurisdiction": "India", "status": "active"},
    {"id": "BNSS_2023", "name": "BNSS_2023",
     "full_title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
     "year": 2023, "jurisdiction": "India", "status": "active"},
    {"id": "BSA_2023", "name": "BSA_2023",
     "full_title": "Bharatiya Sakshya Adhiniyam, 2023",
     "year": 2023, "jurisdiction": "India", "status": "active"},
    {"id": "LIMITATION_ACT_1963", "name": "Limitation_Act_1963",
     "full_title": "Limitation Act, 1963",
     "year": 1963, "jurisdiction": "India", "status": "active"},
]


def seed_statutes(driver):
    """MERGE seed statutes."""
    for s in SEED_STATUTES:
        driver.execute_query(
            """
            MERGE (st:Statute {id: $id})
            SET st += $props
            """,
            id=s["id"],
            props=s,
            database_=DB,
        )
    print(f"  [ok] {len(SEED_STATUTES)} statutes merged")


def main():
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        print("[ingest.sections] connected")
        seed_statutes(driver)
        n = driver.execute_query(
            "MATCH (n) RETURN count(n) AS c", database_=DB
        )[0][0]["c"]
        print(f"[ingest.sections] done — {n} total nodes")


if __name__ == "__main__":
    main()
