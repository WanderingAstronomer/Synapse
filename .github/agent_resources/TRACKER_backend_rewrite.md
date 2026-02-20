# Tracker: Backend Rewrite

## [Phase 1: Infrastructure & Schema]
- [ ] Update `pyproject.toml` (Dependencies) <!-- id: 1 -->
- [ ] Create `synapse/database/connection.py` <!-- id: 2 -->
- [ ] Create `synapse/database/schema.sql` <!-- id: 3 -->
- [ ] Create `synapse/database/schema.py` (Initializer) <!-- id: 4 -->

## [Phase 2: Core Services Migration]
- [ ] Refactor `synapse/services/event_lake_writer.py` <!-- id: 5 -->
- [ ] Verify basic event writing <!-- id: 6 -->

## [Phase 3: Historical Backfill]
- [ ] Create `synapse/services/backfill.py` <!-- id: 7 -->
- [ ] Integrate with Bot Startup <!-- id: 8 -->
