"""
GitHub Stats Service

Service layer that wraps the bash script functionality for gathering
GitHub organization repository statistics.
"""

import asyncio
import csv
import io
import os
import re
import secrets
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx


class JobStatus(str, Enum):
    """Status of an analysis job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisConfig:
    """Configuration for repository analysis."""
    organizations: list[str] = field(default_factory=list)
    repo_list: list[str] = field(default_factory=list)
    hostname: str = "github.com"
    output_format: str = "CSV"
    repo_page_size: int = 10
    extra_page_size: int = 50
    token_type: str = "user"
    analyze_repo_conflicts: bool = False
    analyze_team_conflicts: bool = False
    token: Optional[str] = None


@dataclass
class AnalysisJob:
    """Represents a running or completed analysis job."""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    config: AnalysisConfig = field(default_factory=AnalysisConfig)
    progress: int = 0
    message: str = ""
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_file: Optional[str] = None
    # Progress tracking for current repo
    current_repo: Optional[str] = None
    total_repos: int = 0
    processed_repos: int = 0
    # Script output for display
    output_lines: list[str] = field(default_factory=list)
    # Process control
    _process: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)
    cancelled: bool = False


# In-memory job storage (in production, use Redis or database)
_jobs: dict[str, AnalysisJob] = {}


def get_script_path() -> Path:
    """Get the path to the gh-repo-stats script."""
    # Navigate from ui/services/github_stats.py to gh-repo-stats
    current_dir = Path(__file__).parent.parent.parent
    return current_dir / "gh-repo-stats"


async def validate_token(token: str, hostname: str = "github.com") -> tuple[bool, str]:
    """
    Validate a GitHub token by attempting to authenticate.
    
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        if hostname == "github.com":
            api_url = "https://api.github.com/user"
        else:
            api_url = f"https://{hostname}/api/v3/user"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return True, f"Authenticated as {user_data.get('login', 'unknown')}"
            elif response.status_code == 401:
                return False, "Invalid or expired token"
            elif response.status_code == 403:
                error_msg = response.json().get("message", "Access forbidden")
                return False, f"Access denied: {error_msg}"
            else:
                return False, f"Unexpected response: {response.status_code}"
    except httpx.TimeoutException:
        return False, "Connection timed out"
    except httpx.RequestError as e:
        return False, f"Connection error: {str(e)}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"


async def check_rate_limit(token: str, hostname: str = "github.com") -> dict:
    """
    Check GitHub API rate limit status.
    
    Returns:
        Dict with rate limit info
    """
    try:
        if hostname == "github.com":
            api_url = "https://api.github.com/rate_limit"
        else:
            api_url = f"https://{hostname}/api/v3/rate_limit"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "graphql_remaining": data.get("resources", {}).get("graphql", {}).get("remaining", 0),
                    "graphql_limit": data.get("resources", {}).get("graphql", {}).get("limit", 0),
                    "core_remaining": data.get("resources", {}).get("core", {}).get("remaining", 0),
                    "core_limit": data.get("resources", {}).get("core", {}).get("limit", 0),
                    "reset_time": data.get("resources", {}).get("graphql", {}).get("reset", 0),
                }
            return {"error": f"Failed to get rate limit: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def create_job(config: AnalysisConfig) -> AnalysisJob:
    """Create a new analysis job."""
    job_id = secrets.token_urlsafe(16)
    job = AnalysisJob(
        job_id=job_id,
        config=config,
        status=JobStatus.PENDING
    )
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Optional[AnalysisJob]:
    """Get a job by ID."""
    return _jobs.get(job_id)


def get_all_jobs() -> list[AnalysisJob]:
    """Get all jobs, sorted by start time (most recent first)."""
    jobs = list(_jobs.values())
    # Sort by started_at descending (None values last)
    jobs.sort(key=lambda j: j.started_at or datetime.min, reverse=True)
    return jobs


def get_recent_jobs(limit: int = 10) -> list[AnalysisJob]:
    """Get recent jobs, limited to a specified number."""
    return get_all_jobs()[:limit]


async def cancel_job(job_id: str) -> tuple[bool, str]:
    """
    Cancel a running job.
    
    Returns:
        Tuple of (success, message)
    """
    job = get_job(job_id)
    if not job:
        return False, "Job not found"
    
    if job.status != JobStatus.RUNNING:
        return False, f"Job is not running (current status: {job.status.value})"
    
    # Set cancelled flag
    job.cancelled = True
    job.message = "Cancelling..."
    
    # Terminate the process if it exists
    if job._process:
        try:
            job._process.terminate()
            # Give it a moment to terminate gracefully
            try:
                await asyncio.wait_for(job._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate
                job._process.kill()
        except ProcessLookupError:
            # Process already ended
            pass
        except Exception as e:
            return False, f"Error terminating process: {str(e)}"
    
    return True, "Job cancellation requested"


async def run_analysis(job_id: str) -> None:
    """
    Run the repository analysis for a job.
    
    This executes the gh-repo-stats bash script with the configured options.
    Streams output to track progress of individual repositories.
    """
    job = get_job(job_id)
    if not job:
        return
    
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now()
    job.message = "Starting analysis..."
    
    try:
        # Create a temporary directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create org input file if multiple orgs
            org_file = None
            if len(job.config.organizations) > 1:
                org_file = Path(temp_dir) / "orgs.txt"
                org_file.write_text("\n".join(job.config.organizations))
            
            # Create repo list file if specified
            repo_file = None
            if job.config.repo_list:
                repo_file = Path(temp_dir) / "repos.txt"
                repo_file.write_text("\n".join(job.config.repo_list))
                job.total_repos = len(job.config.repo_list)
            
            # Build command
            script_path = get_script_path()
            cmd = [str(script_path)]
            
            # Add organization(s)
            if org_file:
                cmd.extend(["-i", str(org_file)])
            elif job.config.organizations:
                cmd.extend(["-o", job.config.organizations[0]])
            
            # Add hostname if not default
            if job.config.hostname != "github.com":
                cmd.extend(["-H", job.config.hostname])
            
            # Add output format
            cmd.extend(["-O", "CSV"])
            
            # Add page sizes
            cmd.extend(["-p", str(job.config.repo_page_size)])
            cmd.extend(["-e", str(job.config.extra_page_size)])
            
            # Add token type
            cmd.extend(["-y", job.config.token_type])
            
            # Add conflict analysis flags
            if job.config.analyze_repo_conflicts:
                cmd.append("-r")
            if job.config.analyze_team_conflicts:
                cmd.append("-T")
            
            # Add repo list if specified
            if repo_file:
                cmd.extend(["-rl", str(repo_file)])
            
            # Set up environment
            env = os.environ.copy()
            if job.config.token:
                env["GH_TOKEN"] = job.config.token
            if job.config.hostname:
                env["GH_HOST"] = job.config.hostname
            
            job.message = f"Running analysis on {', '.join(job.config.organizations)}..."
            
            # Run the script and stream output for progress tracking
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=temp_dir
            )
            
            # Store process reference for cancellation
            job._process = process
            
            # Track output for progress parsing
            stderr_output = []
            
            # Read stderr line by line to track progress
            async def read_stderr():
                repo_pattern = re.compile(r'Processing\s+(?:repo\s+)?(\d+)\s*/\s*(\d+)(?:\s*:\s*(.+))?', re.IGNORECASE)
                repo_name_pattern = re.compile(r'Analyzing\s+(?:repository\s+)?["\']?([^"\']+)["\']?', re.IGNORECASE)
                total_pattern = re.compile(r'Found\s+(\d+)\s+repositor', re.IGNORECASE)
                
                while True:
                    # Check if job was cancelled
                    if job.cancelled:
                        break
                    
                    line = await process.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').strip()
                    stderr_output.append(decoded)
                    
                    # Store output line for display (keep last 500 lines)
                    if decoded:
                        job.output_lines.append(decoded)
                        if len(job.output_lines) > 500:
                            job.output_lines = job.output_lines[-500:]
                    
                    # Try to parse progress from output
                    # Look for "Processing X/Y" or similar patterns
                    match = repo_pattern.search(decoded)
                    if match:
                        job.processed_repos = int(match.group(1))
                        job.total_repos = int(match.group(2))
                        if match.group(3):
                            job.current_repo = match.group(3).strip()
                        if job.total_repos > 0:
                            job.progress = int((job.processed_repos / job.total_repos) * 100)
                        job.message = f"Processing {job.processed_repos}/{job.total_repos}: {job.current_repo or 'fetching...'}"
                        continue
                    
                    # Look for total repos count
                    total_match = total_pattern.search(decoded)
                    if total_match:
                        job.total_repos = int(total_match.group(1))
                        job.message = f"Found {job.total_repos} repositories to analyze..."
                        continue
                    
                    # Look for repo name being analyzed
                    name_match = repo_name_pattern.search(decoded)
                    if name_match:
                        job.current_repo = name_match.group(1)
                        job.processed_repos += 1
                        if job.total_repos > 0:
                            job.progress = int((job.processed_repos / job.total_repos) * 100)
                        job.message = f"Analyzing: {job.current_repo}"
            
            # Read stdout
            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').strip()
                    # Store stdout output as well
                    if decoded:
                        job.output_lines.append(f"[stdout] {decoded}")
                        if len(job.output_lines) > 500:
                            job.output_lines = job.output_lines[-500:]
            
            # Run both readers concurrently
            await asyncio.gather(read_stderr(), read_stdout())
            
            # Wait for process to complete
            await process.wait()
            
            # Clear process reference
            job._process = None
            
            # Check if job was cancelled
            if job.cancelled:
                job.status = JobStatus.FAILED
                job.message = "Analysis cancelled by user"
                job.output_lines.append(">>> Analysis cancelled by user <<<")
                job.current_repo = None
                job.completed_at = datetime.now()
                return
            
            if process.returncode != 0:
                job.status = JobStatus.FAILED
                job.errors.append(f"Script failed with code {process.returncode}")
                if stderr_output:
                    job.errors.append("\n".join(stderr_output[-10:]))  # Last 10 lines
                job.message = "Analysis failed"
                job.current_repo = None
                job.completed_at = datetime.now()
                return
            
            # Find and parse the output CSV file
            csv_files = list(Path(temp_dir).glob("*-all_repos-*.csv"))
            if csv_files:
                job.output_file = str(csv_files[0])
                job.results = parse_csv_results(csv_files[0])
                job.message = f"Analysis complete. Found {len(job.results)} repositories."
                job.processed_repos = len(job.results)
                job.total_repos = len(job.results)
            else:
                job.message = "Analysis complete but no output file found."
            
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.current_repo = None
            job.completed_at = datetime.now()
            
    except Exception as e:
        job.status = JobStatus.FAILED
        job.errors.append(str(e))
        job.message = f"Analysis failed: {str(e)}"
        job.current_repo = None
        job.completed_at = datetime.now()


def parse_csv_results(csv_path: Path) -> list[dict]:
    """Parse CSV results into a list of dictionaries."""
    results = []
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                numeric_fields = [
                    "Repo_Size(mb)", "Record_Count", "Collaborator_Count",
                    "Protected_Branch_Count", "PR_Review_Count", "Milestone_Count",
                    "Issue_Count", "PR_Count", "PR_Review_Comment_Count",
                    "Commit_Comment_Count", "Issue_Comment_Count", "Issue_Event_Count",
                    "Release_Count", "Project_Count", "Branch_Count", "Tag_Count",
                    "Discussion_Count"
                ]
                for field in numeric_fields:
                    if field in row and row[field]:
                        try:
                            row[field] = int(row[field])
                        except ValueError:
                            pass
                
                # Convert boolean fields
                bool_fields = ["Is_Empty", "isFork", "isArchived", "Has_Wiki"]
                for field in bool_fields:
                    if field in row:
                        row[field] = row[field].lower() == "true"
                
                results.append(row)
    except Exception:
        pass
    return results


def results_to_csv(results: list[dict]) -> str:
    """Convert results list to CSV string."""
    if not results:
        return ""
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)
    return output.getvalue()


def calculate_summary(results: list[dict]) -> dict:
    """Calculate summary statistics from results."""
    if not results:
        return {
            "total_repos": 0,
            "total_size_mb": 0,
            "repos_with_issues": 0,
            "avg_record_count": 0,
            "empty_repos": 0,
            "archived_repos": 0,
            "forked_repos": 0,
            "total_prs": 0,
            "total_issues": 0,
        }
    
    total_size = sum(r.get("Repo_Size(mb)", 0) or 0 for r in results)
    total_records = sum(r.get("Record_Count", 0) or 0 for r in results)
    migration_issues = sum(1 for r in results if r.get("Migration_Issue", "").upper() == "TRUE")
    empty_repos = sum(1 for r in results if r.get("Is_Empty", False))
    archived_repos = sum(1 for r in results if r.get("isArchived", False))
    forked_repos = sum(1 for r in results if r.get("isFork", False))
    total_prs = sum(r.get("PR_Count", 0) or 0 for r in results)
    total_issues = sum(r.get("Issue_Count", 0) or 0 for r in results)
    
    return {
        "total_repos": len(results),
        "total_size_mb": total_size,
        "repos_with_issues": migration_issues,
        "avg_record_count": round(total_records / len(results)) if results else 0,
        "empty_repos": empty_repos,
        "archived_repos": archived_repos,
        "forked_repos": forked_repos,
        "total_prs": total_prs,
        "total_issues": total_issues,
    }


# Sample data for testing/development
SAMPLE_DATA = [
    {
        "Org_Name": "sample-org",
        "Repo_Name": "sample-repo-1",
        "Is_Empty": False,
        "Last_Push": "2024-01-15T10:30:00Z",
        "Last_Update": "2024-01-15T10:30:00Z",
        "isFork": False,
        "isArchived": False,
        "Repo_Size(mb)": 25,
        "Record_Count": 1500,
        "Collaborator_Count": 15,
        "Protected_Branch_Count": 2,
        "PR_Review_Count": 45,
        "Milestone_Count": 3,
        "Issue_Count": 120,
        "PR_Count": 85,
        "PR_Review_Comment_Count": 230,
        "Commit_Comment_Count": 12,
        "Issue_Comment_Count": 450,
        "Issue_Event_Count": 890,
        "Release_Count": 15,
        "Project_Count": 2,
        "Branch_Count": 8,
        "Tag_Count": 15,
        "Discussion_Count": 5,
        "Has_Wiki": True,
        "Full_URL": "https://github.com/sample-org/sample-repo-1",
        "Migration_Issue": "FALSE",
        "Created": "2020-03-15T08:00:00Z"
    },
    {
        "Org_Name": "sample-org",
        "Repo_Name": "sample-repo-2",
        "Is_Empty": False,
        "Last_Push": "2024-01-10T14:20:00Z",
        "Last_Update": "2024-01-10T14:20:00Z",
        "isFork": True,
        "isArchived": False,
        "Repo_Size(mb)": 150,
        "Record_Count": 65000,
        "Collaborator_Count": 45,
        "Protected_Branch_Count": 5,
        "PR_Review_Count": 200,
        "Milestone_Count": 8,
        "Issue_Count": 500,
        "PR_Count": 350,
        "PR_Review_Comment_Count": 1200,
        "Commit_Comment_Count": 50,
        "Issue_Comment_Count": 2000,
        "Issue_Event_Count": 4500,
        "Release_Count": 40,
        "Project_Count": 5,
        "Branch_Count": 25,
        "Tag_Count": 40,
        "Discussion_Count": 30,
        "Has_Wiki": True,
        "Full_URL": "https://github.com/sample-org/sample-repo-2",
        "Migration_Issue": "TRUE",
        "Created": "2019-06-20T12:00:00Z"
    },
    {
        "Org_Name": "sample-org",
        "Repo_Name": "archived-repo",
        "Is_Empty": False,
        "Last_Push": "2022-05-01T09:00:00Z",
        "Last_Update": "2022-05-01T09:00:00Z",
        "isFork": False,
        "isArchived": True,
        "Repo_Size(mb)": 5,
        "Record_Count": 200,
        "Collaborator_Count": 3,
        "Protected_Branch_Count": 0,
        "PR_Review_Count": 10,
        "Milestone_Count": 1,
        "Issue_Count": 20,
        "PR_Count": 15,
        "PR_Review_Comment_Count": 30,
        "Commit_Comment_Count": 5,
        "Issue_Comment_Count": 40,
        "Issue_Event_Count": 100,
        "Release_Count": 3,
        "Project_Count": 0,
        "Branch_Count": 2,
        "Tag_Count": 3,
        "Discussion_Count": 0,
        "Has_Wiki": False,
        "Full_URL": "https://github.com/sample-org/archived-repo",
        "Migration_Issue": "FALSE",
        "Created": "2018-01-10T16:00:00Z"
    },
    {
        "Org_Name": "sample-org",
        "Repo_Name": "empty-repo",
        "Is_Empty": True,
        "Last_Push": "",
        "Last_Update": "2024-01-01T08:00:00Z",
        "isFork": False,
        "isArchived": False,
        "Repo_Size(mb)": 0,
        "Record_Count": 0,
        "Collaborator_Count": 1,
        "Protected_Branch_Count": 0,
        "PR_Review_Count": 0,
        "Milestone_Count": 0,
        "Issue_Count": 0,
        "PR_Count": 0,
        "PR_Review_Comment_Count": 0,
        "Commit_Comment_Count": 0,
        "Issue_Comment_Count": 0,
        "Issue_Event_Count": 0,
        "Release_Count": 0,
        "Project_Count": 0,
        "Branch_Count": 0,
        "Tag_Count": 0,
        "Discussion_Count": 0,
        "Has_Wiki": True,
        "Full_URL": "https://github.com/sample-org/empty-repo",
        "Migration_Issue": "FALSE",
        "Created": "2024-01-01T08:00:00Z"
    }
]
