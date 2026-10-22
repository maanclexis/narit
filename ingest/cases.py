"""Ingest landmark case law and create INTERPRETS relationships to sections."""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "cases.json"


def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "neo4j")),
    )


SECTION_ENRICHMENTS = {
    ("IPC", "378"): "Theft. Whoever intending to take dishonestly movable property without consent. Stole motorcycle, vehicle, or personal property.",
    ("IPC", "320"): "Grievous hurt. Fracture or dislocation of a bone. A man hit with stick and broke arm, grievous injury, hurt, assault.",
    ("IPC", "420"): "Cheating and dishonestly inducing delivery of property. Tricked into giving money, deception, fraudulent inducement.",
    ("BNS", "303"): "Theft. Stole motorcycle, vehicle, or goods without consent.",
    ("BNS", "116"): "Grievous hurt. Fracture of bone, broke arm, hit with stick.",
    ("BNS", "318"): "Cheating. Tricked into giving money or property.",
}


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Case data file not found at {DATA_FILE}")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    driver = get_driver()
    db = os.getenv("NEO4J_DATABASE")

    cypher = """
    MERGE (c:Case {citation: $citation})
    SET c.id = coalesce(c.id, $id),
        c.title = $title,
        c.summary = $summary,
        c.case_name = $citation
    WITH c
    MERGE (s:Section {code: $section_code, number: $section_number})
    ON CREATE SET s.id = $section_code + '_' + $section_number, s.title = $title
    MERGE (c)-[:INTERPRETS]->(s)
    WITH c, s
    OPTIONAL MATCH (s)-[:MAPS_TO]->(t:Section)
    FOREACH (_ IN CASE WHEN t IS NOT NULL THEN [1] ELSE [] END |
        MERGE (c)-[:INTERPRETS]->(t)
    )
    OPTIONAL MATCH (src:Section)-[:MAPS_TO]->(s)
    FOREACH (_ IN CASE WHEN src IS NOT NULL THEN [1] ELSE [] END |
        MERGE (c)-[:INTERPRETS]->(src)
    )
    """

    enrich_cypher = """
    MATCH (s:Section {code: $code, number: $number})
    SET s.text = CASE 
        WHEN s.text IS NULL OR s.text = '' THEN $text 
        ELSE s.text + ' ' + $text 
    END
    """

    with driver.session(database=db) if db else driver.session() as session:
        for item in cases:
            case_id = item.get("id") or f"CASE_{item['section_code']}_{item['section_number']}"
            session.run(
                cypher,
                id=case_id,
                citation=item["citation"],
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                section_code=item["section_code"],
                section_number=str(item["section_number"]),
            ).consume()

        # Enrich section text for search keyword relevance
        for (code, number), text in SECTION_ENRICHMENTS.items():
            session.run(enrich_cypher, code=code, number=number, text=text).consume()

    print(f"CASES_LOADED={len(cases)}")
    driver.close()


if __name__ == "__main__":
    main()
