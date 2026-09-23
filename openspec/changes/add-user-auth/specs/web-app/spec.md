## ADDED Requirements

### Requirement: Placeholder home page
The home page (`/`) SHALL be a static page that does not query the database and that links to the API reference at `/docs`.

#### Scenario: Home page renders without the database
- **WHEN** the database is stopped and a user opens `http://localhost:3000/`
- **THEN** the page renders and contains a link to `/docs`

## REMOVED Requirements

### Requirement: Demo page reads and writes data end to end
**Reason**: The notes demo only existed to prove the database round trip worked. The user/auth API now exercises the database, and the `notes` table is dropped.
**Migration**: None needed. The notes data was demo-only and is discarded when the migration drops the `notes` table. Use the `/api/*` endpoints (documented at `/docs`) to exercise the database.
