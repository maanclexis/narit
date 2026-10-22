"""Seed statutes and load full corpus of sections into Neo4j.

Usage:  python -m ingest.sections
"""

import json
import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ["NEO4J_URI"]
AUTH = (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
DB = os.environ.get("NEO4J_DATABASE", "neo4j")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
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
    {"id": "IPC_1860", "name": "IPC_1860",
     "full_title": "Indian Penal Code, 1860",
     "year": 1860, "jurisdiction": "India", "status": "repealed"},
]

EXTRA_SPECIAL_SECTIONS = [
    {"id": "NDPS_20", "code": "NDPS", "number": "20",
     "title": "Punishment for contravention in relation to cannabis plant and cannabis",
     "text": "Whoever, in contravention of any provision of this Act cultivates cannabis or produces, manufactures, possesses, sells, purchases, transports cannabis.",
     "statute_id": "NDPS_ACT_1985"},
    {"id": "NDPS_21", "code": "NDPS", "number": "21",
     "title": "Punishment for contravention in relation to manufactured drugs and preparations",
     "text": "Whoever manufactures, possesses, sells, purchases, transports, imports inter-State, exports inter-State or uses any manufactured drug.",
     "statute_id": "NDPS_ACT_1985"},
    {"id": "NDPS_42", "code": "NDPS", "number": "42",
     "title": "Power of entry, search, seizure and arrest without warrant",
     "text": "Power of entry, search, seizure and arrest without warrant or authorisation by empowered officer.",
     "statute_id": "NDPS_ACT_1985"},
    {"id": "NDPS_50", "code": "NDPS", "number": "50",
     "title": "Conditions under which search of persons shall be conducted",
     "text": "Mandatory procedure to inform person of right to be searched before Gazetted Officer or Magistrate.",
     "statute_id": "NDPS_ACT_1985"},
    {"id": "BNSS_35", "code": "BNSS", "number": "35",
     "title": "When police may arrest without warrant",
     "text": "Any police officer may without an order from a Magistrate and without a warrant arrest any person committing cognizable offence.",
     "statute_id": "BNSS_2023"},
    {"id": "BNSS_105", "code": "BNSS", "number": "105",
     "title": "Recording of search and seizure through audio-video electronic means",
     "text": "The process of conducting search of a place or taking possession of any property, article or device shall be recorded through audio-video electronic means.",
     "statute_id": "BNSS_2023"},
    {"id": "BSA_61", "code": "BSA", "number": "61",
     "title": "Admissibility of electronic or digital record",
     "text": "Nothing in this Adhiniyam shall apply to deny admissibility of electronic record or evidence.",
     "statute_id": "BSA_2023"},
    {"id": "BSA_63", "code": "BSA", "number": "63",
     "title": "Admissibility of electronic records and certificate requirement",
     "text": "Conditions for admissibility of electronic records and certificate requirement under BSA.",
     "statute_id": "BSA_2023"},
    {"id": "LIMITATION_5", "code": "LIMITATION", "number": "5",
     "title": "Extension of prescribed period in certain cases",
     "text": "Any appeal or application may be admitted after the prescribed period if sufficient cause is shown (condonation of delay).",
     "statute_id": "LIMITATION_ACT_1963"},
]


def seed_statutes(driver):
    """MERGE all statutes."""
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


def load_sections(driver):
    """Load full corpus of sections from CSV and enrichments."""
    csv_file = DATA_DIR / "ipc_bns_raw.csv"
    sections = []

    if csv_file.exists():
        df = pd.read_csv(csv_file)
        # IPC sections
        for _, row in df.iterrows():
            ipc_num = str(row.get("IPC Section", "")).strip()
            if ipc_num and ipc_num.lower() != "nan":
                sections.append({
                    "id": f"IPC_{ipc_num}",
                    "code": "IPC",
                    "number": ipc_num,
                    "title": str(row.get("IPC Heading", "")).strip(),
                    "text": str(row.get("IPC Descriptions", "")).strip(),
                    "statute_id": "IPC_1860"
                })

            bns_num = str(row.get("BNS Section", "")).strip()
            if bns_num and bns_num.lower() not in ("nan", "—", "-", "removed"):
                sections.append({
                    "id": f"BNS_{bns_num}",
                    "code": "BNS",
                    "number": bns_num,
                    "title": str(row.get("BNS Heading", "")).strip(),
                    "text": str(row.get("BNS description", "")).strip(),
                    "statute_id": "BNS_2023"
                })

    sections.extend(EXTRA_SPECIAL_SECTIONS)

    # Deduplicate by (code, number)
    seen = set()
    unique_sections = []
    for s in sections:
        k = (s["code"], s["number"])
        if k not in seen:
            seen.add(k)
            unique_sections.append(s)

    q = """
    UNWIND $batch AS s
    MERGE (sec:Section {code: s.code, number: s.number})
    SET sec.id = coalesce(sec.id, s.id),
        sec.title = s.title,
        sec.text = s.text,
        sec.statute_id = s.statute_id
    WITH sec, s
    MATCH (st:Statute {id: s.statute_id})
    MERGE (sec)-[:BELONGS_TO]->(st)
    """

    batch_size = 100
    with driver.session(database=DB) as session:
        for i in range(0, len(unique_sections), batch_size):
            batch = unique_sections[i : i + batch_size]
            session.run(q, batch=batch).consume()

    print(f"  [ok] {len(unique_sections)} unique sections loaded")


def main():
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        print("[ingest.sections] connected")
        seed_statutes(driver)
        load_sections(driver)
        n = driver.execute_query(
            "MATCH (s:Section) RETURN count(s) AS c", database_=DB
        )[0][0]["c"]
        print(f"[ingest.sections] done — {n} total sections in graph")


if __name__ == "__main__":
    main()
