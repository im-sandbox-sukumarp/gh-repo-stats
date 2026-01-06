"""
Routes for gh-repo-stats Web UI

Defines all API endpoints and page routes.
"""

import asyncio
import secrets
import subprocess
import sys
import re
from typing import Optional

import httpx
import starlette

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .services.github_stats import (
    AnalysisConfig,
    AnalysisJob,
    JobStatus,
    SAMPLE_DATA,
    calculate_summary,
    cancel_job,
    check_rate_limit,
    create_job,
    get_job,
    get_recent_jobs,
    results_to_csv,
    run_analysis,
    validate_token,
)


async def get_system_info() -> dict:
    """Gather system dependency information."""
    info = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "starlette_version": starlette.__version__,
        "gh_cli": {
            "installed": False,
            "version": None,
            "date": None,
            "update_available": False,
            "latest_version": None,
        },
        "jq": {
            "installed": False,
            "version": None,
        },
    }
    
    # Check gh CLI
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info["gh_cli"]["installed"] = True
            # Parse version: "gh version 2.40.1 (2024-01-15)"
            version_match = re.search(r'gh version ([\d.]+)', result.stdout)
            date_match = re.search(r'\((\d{4}-\d{2}-\d{2})\)', result.stdout)
            if version_match:
                info["gh_cli"]["version"] = version_match.group(1)
            if date_match:
                info["gh_cli"]["date"] = date_match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    # Check for gh CLI updates (async)
    if info["gh_cli"]["installed"] and info["gh_cli"]["version"]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://api.github.com/repos/cli/cli/releases/latest",
                    headers={"Accept": "application/vnd.github+json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    latest = data.get("tag_name", "").lstrip("v")
                    info["gh_cli"]["latest_version"] = latest
                    if latest and info["gh_cli"]["version"]:
                        # Simple version comparison
                        current_parts = [int(x) for x in info["gh_cli"]["version"].split(".")]
                        latest_parts = [int(x) for x in latest.split(".")]
                        info["gh_cli"]["update_available"] = latest_parts > current_parts
        except Exception:
            pass
    
    # Check jq
    try:
        result = subprocess.run(
            ["jq", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info["jq"]["installed"] = True
            # Parse version: "jq-1.6" or "jq-1.7.1"
            version_match = re.search(r'jq-([\d.]+)', result.stdout)
            if version_match:
                info["jq"]["version"] = version_match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    # Check gh-repo-stats extension
    info["gh_repo_stats"] = {
        "installed": False,
        "version": None,
    }
    try:
        result = subprocess.run(
            ["gh", "extension", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Look for gh-repo-stats in the extension list
            for line in result.stdout.splitlines():
                if "repo-stats" in line.lower() or "gh-repo-stats" in line.lower():
                    info["gh_repo_stats"]["installed"] = True
                    # Try to extract version from the line
                    version_match = re.search(r'v?([\d.]+)', line)
                    if version_match:
                        info["gh_repo_stats"]["version"] = version_match.group(1)
                    else:
                        info["gh_repo_stats"]["version"] = "installed"
                    break
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    return info


async def home(request: Request) -> HTMLResponse:
    """Render the home page with the analysis form."""
    system_info = await get_system_info()
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "csrf_token": secrets.token_urlsafe(32),
            "system_info": system_info,
        }
    )


async def task_details_page(request: Request) -> HTMLResponse:
    """Render the task details page."""
    job_id = request.path_params.get("job_id", "")
    
    if not job_id:
        return HTMLResponse(
            content="<h1>No job ID provided</h1><p><a href='/'>Go back</a></p>",
            status_code=400
        )
    
    job = get_job(job_id)
    if not job:
        return HTMLResponse(
            content="<h1>Task not found</h1><p><a href='/'>Go back</a></p>",
            status_code=404
        )
    
    return request.app.state.templates.TemplateResponse(
        "task_details.html",
        {
            "request": request,
            "job": job,
            "job_id": job_id,
        }
    )


async def results_page(request: Request) -> HTMLResponse:
    """Render the results page."""
    job_id = request.query_params.get("job_id", "")
    use_sample = request.query_params.get("sample", "") == "true"
    
    if use_sample:
        # Use sample data for demo/testing
        results = SAMPLE_DATA
        summary = calculate_summary(results)
        return request.app.state.templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "results": results,
                "summary": summary,
                "job_id": "sample",
                "is_sample": True,
            }
        )
    
    if not job_id:
        return HTMLResponse(
            content="<h1>No job ID provided</h1><p><a href='/'>Go back</a></p>",
            status_code=400
        )
    
    job = get_job(job_id)
    if not job:
        return HTMLResponse(
            content="<h1>Job not found</h1><p><a href='/'>Go back</a></p>",
            status_code=404
        )
    
    summary = calculate_summary(job.results)
    
    return request.app.state.templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "results": job.results,
            "summary": summary,
            "job": job,
            "job_id": job_id,
            "is_sample": False,
        }
    )


async def api_analyze(request: Request) -> JSONResponse:
    """
    Start a new analysis job.
    
    POST /api/analyze
    
    Body (form-data or JSON):
        - organizations: comma-separated list of org names OR
        - org_file: uploaded file with org names (one per line)
        - repo_list: optional comma-separated list of repos
        - hostname: GitHub hostname (default: github.com)
        - repo_page_size: pagination size for repos (default: 10)
        - extra_page_size: pagination size for extra queries (default: 50)
        - token_type: 'user' or 'app' (default: user)
        - analyze_repo_conflicts: boolean
        - analyze_team_conflicts: boolean
        - token: GitHub token (optional, uses environment if not provided)
    
    Returns:
        JSON with job_id for tracking
    """
    try:
        # Parse form data
        form = await request.form()
        
        # Get organizations
        organizations = []
        org_input = form.get("organizations", "")
        if org_input:
            # Parse comma or newline separated orgs
            organizations = [
                org.strip() 
                for org in str(org_input).replace(",", "\n").split("\n") 
                if org.strip()
            ]
        
        # Check for file upload
        org_file = form.get("org_file")
        if org_file and hasattr(org_file, "read"):
            content = await org_file.read()
            file_orgs = [
                line.strip() 
                for line in content.decode("utf-8").split("\n") 
                if line.strip()
            ]
            organizations.extend(file_orgs)
        
        if not organizations:
            return JSONResponse(
                {"error": "At least one organization is required"},
                status_code=400
            )
        
        # Get repo list
        repo_list = []
        repo_input = form.get("repo_list", "")
        if repo_input:
            repo_list = [
                repo.strip() 
                for repo in str(repo_input).replace(",", "\n").split("\n") 
                if repo.strip()
            ]
        
        # Get configuration options
        hostname = form.get("hostname", "github.com") or "github.com"
        repo_page_size = int(form.get("repo_page_size", 10) or 10)
        extra_page_size = int(form.get("extra_page_size", 50) or 50)
        token_type = form.get("token_type", "user") or "user"
        analyze_repo_conflicts = form.get("analyze_repo_conflicts", "").lower() in ("true", "1", "on")
        analyze_team_conflicts = form.get("analyze_team_conflicts", "").lower() in ("true", "1", "on")
        token = form.get("token", "") or None
        
        # Create config
        config = AnalysisConfig(
            organizations=organizations,
            repo_list=repo_list,
            hostname=str(hostname),
            repo_page_size=repo_page_size,
            extra_page_size=extra_page_size,
            token_type=str(token_type),
            analyze_repo_conflicts=analyze_repo_conflicts,
            analyze_team_conflicts=analyze_team_conflicts,
            token=str(token) if token else None,
        )
        
        # Create and start job
        job = create_job(config)
        
        # Start analysis in background
        asyncio.create_task(run_analysis(job.job_id))
        
        return JSONResponse({
            "job_id": job.job_id,
            "status": job.status.value,
            "message": "Analysis started",
        })
        
    except ValueError as e:
        return JSONResponse(
            {"error": f"Invalid parameter: {str(e)}"},
            status_code=400
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to start analysis: {str(e)}"},
            status_code=500
        )


async def api_status(request: Request) -> JSONResponse:
    """
    Get status of an analysis job.
    
    GET /api/status/{job_id}
    """
    job_id = request.path_params["job_id"]
    job = get_job(job_id)
    
    if not job:
        return JSONResponse(
            {"error": "Job not found"},
            status_code=404
        )
    
    # Check if output is requested
    include_output = request.query_params.get("output", "").lower() == "true"
    
    response_data = {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress": job.progress,
        "message": job.message,
        "errors": job.errors,
        "result_count": len(job.results),
        "current_repo": job.current_repo,
        "total_repos": job.total_repos,
        "processed_repos": job.processed_repos,
        "organizations": job.config.organizations,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    
    if include_output:
        response_data["output_lines"] = job.output_lines
    
    return JSONResponse(response_data)


async def api_cancel(request: Request) -> JSONResponse:
    """
    Cancel a running analysis job.
    
    POST /api/cancel/{job_id}
    """
    job_id = request.path_params["job_id"]
    
    success, message = await cancel_job(job_id)
    
    if success:
        return JSONResponse({
            "success": True,
            "message": message,
        })
    else:
        return JSONResponse(
            {"success": False, "error": message},
            status_code=400 if "not running" in message.lower() else 404
        )


async def api_results(request: Request) -> JSONResponse:
    """
    Get results of a completed analysis job.
    
    GET /api/results/{job_id}
    """
    job_id = request.path_params["job_id"]
    job = get_job(job_id)
    
    if not job:
        return JSONResponse(
            {"error": "Job not found"},
            status_code=404
        )
    
    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
        return JSONResponse({
            "job_id": job.job_id,
            "status": job.status.value,
            "message": "Job is still running",
        })
    
    summary = calculate_summary(job.results)
    
    return JSONResponse({
        "job_id": job.job_id,
        "status": job.status.value,
        "results": job.results,
        "summary": summary,
        "errors": job.errors,
    })


async def api_download(request: Request) -> Response:
    """
    Download results as CSV.
    
    GET /api/download/{job_id}
    """
    job_id = request.path_params["job_id"]
    
    # Handle sample data
    if job_id == "sample":
        csv_content = results_to_csv(SAMPLE_DATA)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=sample-repo-stats.csv"
            }
        )
    
    job = get_job(job_id)
    
    if not job:
        return JSONResponse(
            {"error": "Job not found"},
            status_code=404
        )
    
    if job.status != JobStatus.COMPLETED:
        return JSONResponse(
            {"error": "Job not completed"},
            status_code=400
        )
    
    csv_content = results_to_csv(job.results)
    
    # Generate filename
    orgs = "-".join(job.config.organizations[:3])
    if len(job.config.organizations) > 3:
        orgs += f"-and-{len(job.config.organizations) - 3}-more"
    filename = f"{orgs}-repo-stats.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


async def api_validate_token(request: Request) -> JSONResponse:
    """
    Validate a GitHub token.
    
    POST /api/validate-token
    """
    try:
        form = await request.form()
        token = form.get("token", "")
        hostname = form.get("hostname", "github.com") or "github.com"
        
        if not token:
            return JSONResponse(
                {"valid": False, "message": "No token provided"},
                status_code=400
            )
        
        is_valid, message = await validate_token(str(token), str(hostname))
        
        return JSONResponse({
            "valid": is_valid,
            "message": message,
        })
    except Exception as e:
        return JSONResponse(
            {"valid": False, "message": f"Validation error: {str(e)}"},
            status_code=500
        )


async def api_rate_limit(request: Request) -> JSONResponse:
    """
    Check GitHub API rate limit.
    
    POST /api/rate-limit
    """
    try:
        form = await request.form()
        token = form.get("token", "")
        hostname = form.get("hostname", "github.com") or "github.com"
        
        if not token:
            return JSONResponse(
                {"error": "No token provided"},
                status_code=400
            )
        
        rate_limit = await check_rate_limit(str(token), str(hostname))
        
        return JSONResponse(rate_limit)
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to check rate limit: {str(e)}"},
            status_code=500
        )


async def api_sample_data(request: Request) -> JSONResponse:
    """
    Get sample data for demo/testing.
    
    GET /api/sample
    """
    summary = calculate_summary(SAMPLE_DATA)
    return JSONResponse({
        "results": SAMPLE_DATA,
        "summary": summary,
    })


async def api_recent_jobs(request: Request) -> JSONResponse:
    """
    Get recent analysis jobs.
    
    GET /api/jobs
    """
    limit = int(request.query_params.get("limit", 10))
    jobs = get_recent_jobs(limit)
    
    return JSONResponse({
        "jobs": [
            {
                "job_id": job.job_id,
                "status": job.status.value,
                "progress": job.progress,
                "message": job.message,
                "organizations": job.config.organizations,
                "current_repo": job.current_repo,
                "total_repos": job.total_repos,
                "processed_repos": job.processed_repos,
                "result_count": len(job.results),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in jobs
        ]
    })


async def health(request: Request) -> JSONResponse:
    """
    Health check endpoint.
    
    GET /health
    """
    return JSONResponse({
        "status": "healthy",
        "version": "1.0.0",
    })


# Define routes
routes = [
    Route("/", home, methods=["GET"]),
    Route("/task/{job_id}", task_details_page, methods=["GET"]),
    Route("/results", results_page, methods=["GET"]),
    Route("/api/analyze", api_analyze, methods=["POST"]),
    Route("/api/status/{job_id}", api_status, methods=["GET"]),
    Route("/api/cancel/{job_id}", api_cancel, methods=["POST"]),
    Route("/api/results/{job_id}", api_results, methods=["GET"]),
    Route("/api/download/{job_id}", api_download, methods=["GET"]),
    Route("/api/validate-token", api_validate_token, methods=["POST"]),
    Route("/api/rate-limit", api_rate_limit, methods=["POST"]),
    Route("/api/sample", api_sample_data, methods=["GET"]),
    Route("/api/jobs", api_recent_jobs, methods=["GET"]),
    Route("/health", health, methods=["GET"]),
]
