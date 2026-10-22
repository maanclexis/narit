// ============================================================
// NARIT_Legal_Graph - Schema Initialization
// Run this once in Neo4j Browser on a fresh database.
// Creates uniqueness constraints and performance indexes.
// ============================================================

// --- Uniqueness Constraints ---

CREATE CONSTRAINT statute_name_unique IF NOT EXISTS
FOR (s:Statute) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT section_id_unique IF NOT EXISTS
FOR (s:Section) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT case_id_unique IF NOT EXISTS
FOR (c:Case) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT case_citation_unique IF NOT EXISTS
FOR (c:Case) REQUIRE c.citation IS UNIQUE;

CREATE CONSTRAINT doctrine_name_unique IF NOT EXISTS
FOR (d:Doctrine) REQUIRE d.name IS UNIQUE;

CREATE CONSTRAINT procedure_id_unique IF NOT EXISTS
FOR (p:Procedure) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT manual_id_unique IF NOT EXISTS
FOR (m:PoliceManual) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT fir_number_unique IF NOT EXISTS
FOR (f:FIR) REQUIRE f.fir_number IS UNIQUE;

CREATE CONSTRAINT defence_name_unique IF NOT EXISTS
FOR (d:DefenceArgument) REQUIRE d.name IS UNIQUE;

// --- Performance Indexes ---

CREATE INDEX statute_year_idx IF NOT EXISTS
FOR (s:Statute) ON (s.year);

CREATE INDEX section_statute_idx IF NOT EXISTS
FOR (s:Section) ON (s.statute_id);

CREATE INDEX section_number_idx IF NOT EXISTS
FOR (s:Section) ON (s.number);

CREATE INDEX case_court_idx IF NOT EXISTS
FOR (c:Case) ON (c.court);

CREATE INDEX case_date_idx IF NOT EXISTS
FOR (c:Case) ON (c.judgment_date);

CREATE INDEX doctrine_domain_idx IF NOT EXISTS
FOR (d:Doctrine) ON (d.domain);

CREATE INDEX manual_state_idx IF NOT EXISTS
FOR (m:PoliceManual) ON (m.state);

CREATE INDEX fir_status_idx IF NOT EXISTS
FOR (f:FIR) ON (f.status);

// --- Verification Query ---
// After running the above, execute this to confirm all constraints exist:
// SHOW CONSTRAINTS;
// SHOW INDEXES;
