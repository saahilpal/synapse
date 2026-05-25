# Synapse visualizer REST API

The API layer is exposed locally to drive the interactive Visual Explorer. It implements query limits and secret redaction on all payloads.

## Endpoints

### 1. System Status
- **URL**: `/api/v1/status`
- **Method**: `GET`
- **Description**: Returns database statistics, current git branch, head commit, and active context hash.

### 2. Evolution Timeline
- **URL**: `/api/v1/timeline`
- **Method**: `GET`
- **Params**:
  - `branch` (optional, string): Filter timeline to branch.
  - `limit` (optional, integer, default: 50, max: 100): Limit number of events.
- **Description**: Returns a chronologically sorted sequence of context commits and repository scan operations.

### 3. Graph Projections
- **URL**: `/api/v1/projection/{context_hash}/{kind}`
- **Method**: `GET`
- **Params**:
  - `prefix` (optional, string): Scope subsystem directory search.
  - `compare_with` (optional, string): Scope context hash to compare against.
- **Description**: Evaluates and returns the visual graph slice of type `kind` (`overview`, `subsystem`, `replay`, `drift`, `assumption`, `incident`, `branch`) for the given context. Results are cached inside SQLite.

### 4. System Assumptions
- **URL**: `/api/v1/assumptions`
- **Method**: `GET`
- **Params**:
  - `context_hash` (optional, string): Target context state.
- **Description**: Lists all active and invalidated architectural assumptions with safe markdown rendering.

### 5. Log Note
- **URL**: `/api/v1/note`
- **Method**: `POST`
- **Body**:
  ```json
  { "message": "Manual documentation or note description" }
  ```
- **Description**: Appends a manual note to the cognition store.

### 6. Record Incident
- **URL**: `/api/v1/incident`
- **Method**: `POST`
- **Body**:
  ```json
  { "title": "Incident title", "summary": "Detailed description of incident" }
  ```
- **Description**: Records a system incident linked to current context state.
