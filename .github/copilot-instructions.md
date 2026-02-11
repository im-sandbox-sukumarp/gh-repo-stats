# Copilot Instructions for gh-repo-stats

## Project Overview

`gh-repo-stats` is a GitHub CLI extension for scanning GitHub organizations to gather repository statistics for migration planning. It consists of two components:

1. **CLI Tool** (`gh-repo-stats`): Bash script using GitHub GraphQL API via `gh` CLI
2. **Web UI** (`ui/`): Python/Starlette async web interface that wraps the CLI tool

## Architecture

```
gh-repo-stats (bash CLI)    ← Primary tool, runs GraphQL queries
    ↑
ui/services/github_stats.py ← Spawns CLI as subprocess, parses output
    ↑
ui/routes.py                ← REST API endpoints
    ↑
ui/app.py                   ← Starlette ASGI application
```

### Key Design Decisions
- CLI outputs CSV files; Web UI parses these for display
- Progress tracked by parsing stderr line-by-line with specific regex patterns
- In-memory job storage (`_jobs` dict) - no database required
- GraphQL pagination with configurable page sizes to prevent timeouts
- Tempfile directories isolate each job's output (deleted after parsing)
- Subprocess cancellation via process termination with graceful timeout
- Form uploads handled as multipart with file reading via `await file.read()`

## Code Conventions

### Bash (CLI Script)
- Functions use **PascalCase**: `GetRepos()`, `ParseRepoData()`, `CheckAPILimit()`
- Global constants are **SCREAMING_SNAKE_CASE**: `SLEEP`, `REPO_PAGE_SIZE`
- Debug output via `Debug()` function, controlled by `-d` flag
- All API calls use `gh api` command (GraphQL or REST endpoints)
- Return data via `echo` to stdout; errors via exit codes
- Section headers format: `#### Function FunctionName ##`

### Python (Web UI)
- **Type hints required** on all functions: `def get_job(job_id: str) -> Optional[AnalysisJob]:`
- **Dataclasses** for all data models: `AnalysisConfig`, `AnalysisJob`
- **Async handlers** for all routes using `async def`
- Service layer in `ui/services/` wraps external calls (subprocess, HTTP)
- Progress tracked via regex patterns on stderr (3 patterns in `read_stderr()`)
- Subprocess spawned with `asyncio.create_subprocess_exec()` for concurrent reading
- HTML escaping with `escapeHtml()` to prevent XSS in frontend templates

### JavaScript (Frontend)
- **Vanilla JS**, no frameworks (pure DOM manipulation)
- **Initialization pattern**: `initTheme()`, `initAnalysisForm()`, `initResultsPage()`
- DOM queries: `document.getElementById()`, `querySelector()` only
- Utility functions: `showToast(message, type)`, `formatDate()`, `formatNumber()`
- Theme toggle stored in localStorage under `theme` key

## Development Workflows

### Running Locally
```bash
# CLI usage
gh repo-stats -o <ORG_NAME>

# Web UI (auto-creates venv at ~/.gh-repo-stats-ui/venv/)
gh repo-stats --browse-ui

# Custom port
gh repo-stats --browse-ui --ui-port 9000
```

### Testing
```bash
# Run bash tests
./test/gh-repo-stats.test.sh

# Test Web UI with sample data
curl http://127.0.0.1:8765/api/sample
```

### Dependencies
- CLI requires: `gh` CLI (v2.8+), `jq`
- Web UI requires: Python 3.9+, packages in `ui/requirements.txt`:
  - `starlette` (ASGI framework)
  - `uvicorn` (ASGI server)
  - `jinja2` (templating)
  - `httpx` (async HTTP client)
  - `python-multipart` (form uploads)

## Implementation Patterns

### Subprocess Output Parsing (Web UI)
Progress extracted via three regex patterns on stderr (lines prefixed with `Processing`, `Analyzing`, `Found`):
```python
repo_pattern = re.compile(r'Processing\s+(?:repo\s+)?(\d+)\s*/\s*(\d+)(?:\s*:\s*(.+))?', re.IGNORECASE)
name_pattern = re.compile(r'Analyzing\s+(?:repository\s+)?["\']?([^"\']+)["\']?', re.IGNORECASE)
total_pattern = re.compile(r'Found\s+(\d+)\s+repositor', re.IGNORECASE)
```

### Job Lifecycle & Cancellation
1. Create job with `AnalysisConfig`
2. Start async `run_analysis(job_id)` via `asyncio.create_task()`
3. Monitor via `/api/status/{job_id}` endpoint
4. Cancel via `/api/cancel/{job_id}` (terminates process, sets `cancelled=True`)
5. Process termination: try graceful, timeout 5s, then force kill

### Form Parsing Pattern
```python
form = await request.form()
# File uploads: org_file = form.get("org_file")
# Text fields: organizations = str(form.get("organizations", ""))
# Split by comma or newline and strip whitespace
```

### GraphQL Pagination (CLI)
Cursor-based pagination in `GetRepos()`, `GetNextIssues()`, `GetNextPullRequests()`:
```bash
HAS_NEXT_PAGE=$(echo "${DATA_BLOCK}" | jq -r '.data.organization.repositories.pageInfo.hasNextPage')
NEXT_CURSOR=$(echo "${DATA_BLOCK}" | jq -r '.data.organization.repositories.pageInfo.endCursor')
```

### Environment Setup for Web UI
- Python venv created at: `~/.gh-repo-stats-ui/venv/`
- Respects environment variables: `GH_TOKEN`, `GH_HOST`, `GH_DEBUG`
- Middleware configured: `TrustedHostMiddleware`, `CORSMiddleware`

## Key Files & Their Roles

| File | Purpose | Key Patterns |
|------|---------|--------------|
| `gh-repo-stats` | CLI script, all bash functions | PascalCase functions, GraphQL queries, stderr progress |
| `ui/app.py` | Starlette app setup, middleware | ASGI factory, Jinja2 templates, startup/shutdown hooks |
| `ui/routes.py` | API endpoints & page routes | Async handlers, form parsing, JSON responses, HTML templates |
| `ui/services/github_stats.py` | Job mgt & subprocess execution | Dataclasses, asyncio subprocess, regex progress parsing, CSV parsing |
| `ui/static/js/app.js` | Frontend interactivity | Vanilla JS, localStorage, toast notifications, fetch API |
| `ui/templates/` | Jinja2 HTML templates | Form rendering, results table, progress display |

## Migration Issue Detection
Repositories flagged with `Migration_Issue=TRUE` based on:
- Record count ≥ **60,000** objects
- Repository size > **1.5 GB**

Detection logic in CLI's `MarkMigrationIssues()` function; Web UI displays in results table.

## Error Handling
- CLI: exit codes > 0 indicate failure; errors via stderr
- Web UI: JSONResponse with status codes (400 bad request, 404 not found, 500 server error)
- Subprocess fails when: returncode != 0, missing output CSV, or timeout
- HTTP validation via httpx: timeouts (10s default), connection errors caught

## Environment Variables
- `GH_TOKEN`: GitHub authentication token (CLI & Web UI)
- `GH_HOST`: GitHub Enterprise Server hostname (default: github.com)
- `GH_DEBUG`: Enable debug mode (`true`, `1`, or `api`)
- `GITHUB_TOKEN_TYPE`: Token type (`user` or `app`, default: `user`)
