import json, os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "neo4j")),
    )


def main():
    rows = json.load(open("data/ipc_bns_mapping.json"))
    driver = get_driver()
    db = os.getenv("NEO4J_DATABASE")

    q = """
    UNWIND $batch AS r
    MERGE (i:Section {code:'IPC', number:r.ipc})
    ON CREATE SET i.title = r.title, i.id = 'IPC_' + r.ipc
    ON MATCH SET i.id = coalesce(i.id, 'IPC_' + r.ipc)
    MERGE (b:Section {code:'BNS', number:r.bns})
    ON CREATE SET b.title = r.title, b.id = 'BNS_' + r.bns
    ON MATCH SET b.id = coalesce(b.id, 'BNS_' + r.bns)
    MERGE (i)-[:MAPS_TO]->(b)
    """

    batch_size = 100
    with driver.session(database=db) if db else driver.session() as s:
        for idx in range(0, len(rows), batch_size):
            batch = [
                {"ipc": str(r["ipc"]), "bns": str(r["bns"]), "title": r["title"]}
                for r in rows[idx : idx + batch_size]
            ]
            s.run(q, batch=batch).consume()

    print(f"MAPPINGS_LOADED={len(rows)}")
    driver.close()


if __name__ == "__main__":
    main()
