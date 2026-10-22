# NARIT Legal Graph API

Indian Criminal Law knowledge graph (NDPS, BNS, BNSS, BSA, Limitation Act, Police Manuals) backed by Neo4j Aura, exposed via FastAPI.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # edit with your Aura creds
uvicorn api.main:app --reload
```

## Project Structure

```
NARIT_Legal_Graph/
├── api/                    # FastAPI application
│   ├── main.py             # App entrypoint, lifespan, CORS
│   ├── db.py               # Neo4j driver singleton
│   ├── routers/
│   │   ├── statutes.py     # Statute & Section endpoints
│   │   ├── cases.py        # Case search, citation network
│   │   ├── doctrines.py    # Doctrine lookup & traversal
│   │   ├── procedures.py   # Procedure chain walking
│   │   ├── firs.py         # FIR analysis & compliance check
│   │   └── health.py       # Health check
│   └── schemas.py          # Pydantic response models
├── ingest/                 # Data loading scripts
│   ├── sections.py         # Load statutes & sections
│   └── cases.py            # Load case law
├── ontology/               # Graph ontology definition
│   └── narit_ontology.json
├── scripts/                # Cypher scripts
│   └── 01_init_schema.cypher
├── tests/
│   └── test_health.py
├── .env.example
├── .gitignore
├── Dockerfile
├── render.yaml
├── requirements.txt
├── Makefile
└── README.md
```

## Deployment (Render)

1. Push to GitHub
2. Create a new **Web Service** on Render
3. Set environment variables: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
4. Render auto-detects `render.yaml` and deploys

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Connection health check |
| GET | `/statutes` | List all statutes |
| GET | `/statutes/{name}/sections` | Sections of a statute |
| GET | `/sections/{id}` | Section detail + related cases |
| GET | `/sections/{id}/mapped` | Cross-statute mappings (IPC→BNS) |
| GET | `/cases` | Search cases by court, date range |
| GET | `/cases/{id}` | Case detail + citation network |
| GET | `/cases/{id}/cites` | Outbound citations with treatment |
| GET | `/cases/{id}/cited-by` | Inbound citations |
| GET | `/doctrines` | List doctrines by domain |
| GET | `/doctrines/{name}/cases` | Cases establishing/applying a doctrine |
| GET | `/procedures/{id}/chain` | Walk the PRECEDES chain |
| GET | `/firs/{fir_number}` | FIR detail + charged sections |
| GET | `/firs/{fir_number}/compliance` | Check mandatory procedure compliance |
