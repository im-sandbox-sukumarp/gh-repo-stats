# Web UI for gh-repo-stats

## Overview
Create a modern, responsive web application for the `gh-repo-stats` GitHub CLI extension that allows users to analyze GitHub organization repositories through a browser-based interface instead of the command line.

## Project Structure
Create a new `ui/` directory at the repository root with the following structure:
```
ui/
├── __init__.py
├── app.py                 # Main Starlette application
├── routes.py              # API and page routes
├── services/
│   ├── __init__.py
│   └── github_stats.py    # Service layer wrapping the bash script functionality
├── templates/
│   ├── base.html          # Base template with common layout
│   ├── index.html         # Home page with form inputs
│   ├── results.html       # Results display page
│   └── partials/
│       ├── stats_table.html
│       └── error.html
├── static/
│   ├── css/
│   │   └── styles.css     # Custom styles (use modern CSS with CSS variables)
│   └── js/
│       └── app.js         # Frontend JavaScript for interactivity
└── requirements.txt       # Python dependencies
```

## Technology Stack
- **Backend**: Python 3.9+ with Starlette (async web framework)
- **Templating**: Jinja2 templates
- **Frontend**: Vanilla JavaScript with modern CSS (no heavy frameworks)
- **HTTP Server**: Uvicorn
- **Styling**: Modern, clean design with CSS Grid/Flexbox, dark/light mode support

## Core Features

### 1. Home Page (`/`)
- Organization input field (single org name)
- File upload for multiple organizations (newline-delimited text file)
- Repository list input (optional, for filtering specific repos)
- Configuration options matching CLI flags:
  - GitHub hostname (default: github.com)
  - Output format toggle (Table view / CSV download)
  - Repo page size (default: 10)
  - Extra page size (default: 50)
  - Token type selection (user/app)
  - Analyze repo conflicts checkbox
  - Analyze team conflicts checkbox
- "Run Analysis" button with loading state

### 2. Results Page (`/results`)
- Interactive, sortable data table displaying all columns from the CSV output:
  - Org_Name, Repo_Name, Is_Empty, Last_Push, Last_Update
  - isFork, isArchive, Repo_Size(mb), Record_Count
  - Collaborator_Count, Protected_Branch_Count, PR_Review_Count
  - Milestone_Count, Issue_Count, PR_Count, PR_Review_Comment_Count
  - Commit_Comment_Count, Issue_Comment_Count, Issue_Event_Count
  - Release_Count, Project_Count, Branch_Count, Tag_Count
  - Discussion_Count, Has_Wiki, Full_URL, Migration_Issue, Created
- Visual indicators for:
  - Migration issues (highlight repos with potential problems)
  - Empty repositories
  - Archived/forked repositories
- Summary statistics panel showing:
  - Total repositories analyzed
  - Total size across all repos
  - Repos with migration issues
  - Average record count
- Export options: Download as CSV, Copy to clipboard
- Search/filter functionality across all columns

### 3. API Endpoints
- `GET /` - Home page
- `POST /api/analyze` - Start analysis (returns job ID for long-running tasks)
- `GET /api/status/{job_id}` - Check analysis progress
- `GET /api/results/{job_id}` - Get analysis results
- `GET /api/download/{job_id}` - Download results as CSV
- `GET /health` - Health check endpoint

## CLI Integration

### Modify `gh-repo-stats` Script
Add a new flag to the main bash script:
```bash
-b, --browse-ui    : Launch the web UI in the default browser
    --ui-port      : Port for the web UI server (default: 8765)
```

When `--browse-ui` is provided:
1. Check if Python 3.9+ is available
2. Create/activate a virtual environment in `~/.gh-repo-stats-ui/venv/`
3. Install dependencies from `ui/requirements.txt` if not already installed
4. Start the Uvicorn server on the specified port
5. Automatically open `http://localhost:{port}` in the default browser
6. Handle graceful shutdown on CTRL+C

### Environment Variables
The web UI should respect these environment variables:
- `GH_TOKEN` - GitHub authentication token
- `GH_HOST` - GitHub hostname
- `GH_DEBUG` - Enable debug mode

## UI/UX Requirements

### Design Guidelines
- Clean, modern interface inspired by GitHub's design language
- Responsive layout that works on desktop and tablet
- Dark mode support (respects system preference, with manual toggle)
- Accessible (WCAG 2.1 AA compliant)
- Loading states and progress indicators for long-running operations
- Clear error messages with actionable guidance

### Visual Elements
- GitHub-style color palette
- Monospace fonts for code/data
- Icons for status indicators (use inline SVGs)
- Smooth transitions and micro-animations
- Toast notifications for success/error states

## Error Handling
- Validate GitHub token before starting analysis
- Handle rate limiting gracefully with retry UI
- Display meaningful error messages for:
  - Invalid organization names
  - Network failures
  - Authentication errors
  - Timeout errors (with suggestions to reduce page size)
- Log errors to browser console and optionally to a log file

## Security Considerations
- Never log or expose the GitHub token in the UI
- Sanitize all user inputs
- Use CSRF protection for form submissions
- Set appropriate security headers (CSP, X-Frame-Options, etc.)
- Bind to localhost only by default

## Dependencies (`ui/requirements.txt`)
```
starlette>=0.32.0
uvicorn[standard]>=0.24.0
jinja2>=3.1.2
python-multipart>=0.0.6
aiofiles>=23.2.1
httpx>=0.25.0
```

## Testing Considerations
- Include example test commands in comments
- Provide sample data for UI development/testing
- Document manual testing scenarios

## Documentation
- Add a "Web UI" section to the README.md explaining:
  - How to launch the UI (`gh repo-stats --browse-ui`)
  - Available UI features
  - Screenshots of the interface
- Include inline code comments for maintainability
