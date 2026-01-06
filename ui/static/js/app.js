/**
 * gh-repo-stats Web UI - Main JavaScript
 * 
 * Handles interactivity for the web UI including:
 * - Form submission and validation
 * - Theme toggling
 * - Table sorting and filtering
 * - Toast notifications
 * - Progress tracking
 */

// =============================================================================
// Theme Management
// =============================================================================

/**
 * Initialize theme based on system preference or saved preference
 */
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    const theme = savedTheme || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
    });
}

/**
 * Toggle between light and dark themes
 */
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// Initialize theme on page load
initTheme();

// Set up theme toggle button
document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);

// =============================================================================
// Toast Notifications
// =============================================================================

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - 'success' or 'error'
 * @param {number} duration - How long to show the toast (ms)
 */
function showToast(message, type = 'success', duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">
            ${type === 'success' 
                ? '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>'
                : '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
            }
        </span>
        <span class="toast-message">${escapeHtml(message)}</span>
        <button class="toast-close" aria-label="Close notification">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;
    
    // Add close functionality
    toast.querySelector('.toast-close').addEventListener('click', () => {
        removeToast(toast);
    });
    
    container.appendChild(toast);
    
    // Auto-remove after duration
    setTimeout(() => {
        removeToast(toast);
    }, duration);
}

/**
 * Remove a toast with animation
 * @param {HTMLElement} toast - The toast element to remove
 */
function removeToast(toast) {
    toast.classList.add('toast-out');
    setTimeout(() => {
        toast.remove();
    }, 300);
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Escape HTML to prevent XSS
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Format a date string for display
 * @param {string} dateStr - ISO date string
 * @returns {string} Formatted date
 */
function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch {
        return dateStr;
    }
}

/**
 * Format a number with thousands separators
 * @param {number} num - Number to format
 * @returns {string} Formatted number
 */
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

/**
 * Debounce a function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// =============================================================================
// Analysis Form
// =============================================================================

/**
 * Initialize the analysis form
 */
function initAnalysisForm() {
    const form = document.getElementById('analysis-form');
    if (!form) return;
    
    // Token visibility toggle
    const tokenInput = document.getElementById('token');
    const toggleBtn = document.getElementById('toggle-token');
    
    toggleBtn?.addEventListener('click', () => {
        const type = tokenInput.type === 'password' ? 'text' : 'password';
        tokenInput.type = type;
        toggleBtn.querySelector('.icon-eye').classList.toggle('hidden');
        toggleBtn.querySelector('.icon-eye-off').classList.toggle('hidden');
    });
    
    // Token validation
    const validateBtn = document.getElementById('validate-token');
    validateBtn?.addEventListener('click', async () => {
        const token = tokenInput.value.trim();
        const hostname = document.getElementById('hostname').value.trim() || 'github.com';
        const statusEl = document.getElementById('token-status');
        
        if (!token) {
            statusEl.textContent = 'Please enter a token to validate';
            statusEl.className = 'token-status visible error';
            return;
        }
        
        validateBtn.disabled = true;
        statusEl.textContent = 'Validating...';
        statusEl.className = 'token-status visible';
        
        try {
            const formData = new FormData();
            formData.append('token', token);
            formData.append('hostname', hostname);
            
            const response = await fetch('/api/validate-token', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            statusEl.textContent = data.message;
            statusEl.className = `token-status visible ${data.valid ? 'success' : 'error'}`;
        } catch (error) {
            statusEl.textContent = 'Failed to validate token';
            statusEl.className = 'token-status visible error';
        } finally {
            validateBtn.disabled = false;
        }
    });
    
    // File input display
    const fileInput = document.getElementById('org-file');
    const fileDisplay = document.querySelector('.file-input-text');
    
    fileInput?.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            fileDisplay.textContent = fileInput.files[0].name;
        } else {
            fileDisplay.textContent = 'Choose a file or drag it here';
        }
    });
    
    // Form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const submitBtn = document.getElementById('submit-btn');
        const orgsInput = document.getElementById('organizations');
        const fileInputEl = document.getElementById('org-file');
        
        // Validate at least one org is specified
        const hasOrgs = orgsInput.value.trim().length > 0;
        const hasFile = fileInputEl.files.length > 0;
        
        if (!hasOrgs && !hasFile) {
            showToast('Please enter at least one organization or upload a file', 'error');
            orgsInput.focus();
            return;
        }
        
        // Show loading state
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        
        try {
            const formData = new FormData(form);
            
            const response = await fetch('/api/analyze', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to start analysis');
            }
            
            // Show success toast
            showToast(`Analysis started for ${orgsInput.value.trim() || 'uploaded organizations'}. Check progress in Recent Tasks below.`, 'success');
            
            // Reset form
            form.reset();
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
            
            // Refresh recent tasks immediately
            loadRecentTasks();
            
            // Scroll to recent tasks section
            const recentTasksSection = document.getElementById('recent-tasks-section');
            if (recentTasksSection) {
                recentTasksSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            
        } catch (error) {
            showToast(error.message, 'error');
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    });
}

// =============================================================================
// Results Page
// =============================================================================

/**
 * Initialize the results page
 */
function initResultsPage() {
    initTableSort();
    initTableFilter();
    initCopyResults();
    initColumnToggle();
}

/**
 * Initialize table sorting
 */
function initTableSort() {
    const table = document.getElementById('results-table');
    if (!table) return;
    
    const headers = table.querySelectorAll('th.sortable');
    let currentSort = { column: null, direction: 'asc' };
    
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const column = header.dataset.sort;
            
            // Determine sort direction
            if (currentSort.column === column) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.column = column;
                currentSort.direction = 'asc';
            }
            
            // Update header classes
            headers.forEach(h => {
                h.classList.remove('sorted-asc', 'sorted-desc');
            });
            header.classList.add(`sorted-${currentSort.direction}`);
            
            // Sort the table
            sortTable(table, column, currentSort.direction);
        });
    });
}

/**
 * Sort a table by column
 * @param {HTMLTableElement} table - The table to sort
 * @param {string} column - Column key to sort by
 * @param {string} direction - 'asc' or 'desc'
 */
function sortTable(table, column, direction) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const sortedRows = rows.sort((a, b) => {
        let aVal = getCellValue(a, column);
        let bVal = getCellValue(b, column);
        
        // Handle numeric values
        const aNum = parseFloat(aVal);
        const bNum = parseFloat(bVal);
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return direction === 'asc' ? aNum - bNum : bNum - aNum;
        }
        
        // Handle boolean values
        if (aVal === 'true' || aVal === 'false') {
            aVal = aVal === 'true' ? 1 : 0;
            bVal = bVal === 'true' ? 1 : 0;
            return direction === 'asc' ? aVal - bVal : bVal - aVal;
        }
        
        // String comparison
        return direction === 'asc' 
            ? aVal.localeCompare(bVal)
            : bVal.localeCompare(aVal);
    });
    
    // Re-append sorted rows
    sortedRows.forEach(row => tbody.appendChild(row));
}

/**
 * Get the value of a cell for sorting
 * @param {HTMLTableRowElement} row - The row element
 * @param {string} column - Column key
 * @returns {string} Cell value
 */
function getCellValue(row, column) {
    // Try to get from data attribute first
    const dataVal = row.dataset[column.toLowerCase().replace(/[^a-z]/g, '')];
    if (dataVal !== undefined) return dataVal;
    
    // Get from cell content
    const headerIndex = Array.from(row.closest('table').querySelectorAll('th'))
        .findIndex(th => th.dataset.sort === column);
    
    if (headerIndex === -1) return '';
    
    const cell = row.cells[headerIndex];
    return cell?.textContent?.trim() || '';
}

/**
 * Initialize table filtering
 */
function initTableFilter() {
    const searchInput = document.getElementById('table-search');
    const filterSelect = document.getElementById('filter-status');
    const table = document.getElementById('results-table');
    
    if (!table) return;
    
    const filterTable = debounce(() => {
        const searchTerm = searchInput?.value.toLowerCase() || '';
        const filterValue = filterSelect?.value || '';
        
        const rows = table.querySelectorAll('tbody tr');
        let visibleCount = 0;
        
        rows.forEach(row => {
            let visible = true;
            
            // Search filter
            if (searchTerm) {
                const text = row.textContent.toLowerCase();
                visible = text.includes(searchTerm);
            }
            
            // Status filter
            if (visible && filterValue) {
                switch (filterValue) {
                    case 'migration-issue':
                        visible = row.dataset.migration === 'true';
                        break;
                    case 'empty':
                        visible = row.dataset.empty === 'true';
                        break;
                    case 'archived':
                        visible = row.dataset.archived === 'true';
                        break;
                    case 'forked':
                        visible = row.dataset.fork === 'true';
                        break;
                }
            }
            
            row.classList.toggle('hidden-row', !visible);
            if (visible) visibleCount++;
        });
        
        // Update count
        const countEl = document.getElementById('visible-count');
        if (countEl) {
            countEl.textContent = visibleCount;
        }
    }, 200);
    
    searchInput?.addEventListener('input', filterTable);
    filterSelect?.addEventListener('change', filterTable);
}

/**
 * Initialize copy to clipboard functionality
 */
function initCopyResults() {
    const copyBtn = document.getElementById('copy-results');
    if (!copyBtn || !window.resultsData) return;
    
    copyBtn.addEventListener('click', async () => {
        try {
            // Convert results to TSV for easy pasting into spreadsheets
            const headers = Object.keys(window.resultsData[0] || {});
            const tsv = [
                headers.join('\t'),
                ...window.resultsData.map(row => 
                    headers.map(h => row[h] ?? '').join('\t')
                )
            ].join('\n');
            
            await navigator.clipboard.writeText(tsv);
            showToast('Results copied to clipboard', 'success');
        } catch (error) {
            showToast('Failed to copy results', 'error');
        }
    });
}

/**
 * Initialize column toggle functionality
 */
function initColumnToggle() {
    const toggleBtn = document.getElementById('toggle-columns');
    const modal = document.getElementById('column-modal');
    const columnList = document.getElementById('column-list');
    const resetBtn = document.getElementById('reset-columns');
    const applyBtn = document.getElementById('apply-columns');
    const closeBtn = modal?.querySelector('.modal-close');
    const backdrop = modal?.querySelector('.modal-backdrop');
    
    if (!toggleBtn || !modal) return;
    
    const table = document.getElementById('results-table');
    const headers = Array.from(table?.querySelectorAll('th') || []);
    
    // Default visible columns
    const defaultVisible = new Set(headers.map((_, i) => i));
    let visibleColumns = new Set(defaultVisible);
    
    // Load saved preferences
    try {
        const saved = localStorage.getItem('visibleColumns');
        if (saved) {
            visibleColumns = new Set(JSON.parse(saved));
        }
    } catch (e) {
        console.error('Error loading column preferences:', e);
    }
    
    // Populate column list
    const populateColumnList = () => {
        columnList.innerHTML = headers.map((header, index) => `
            <label class="checkbox-label">
                <input type="checkbox" value="${index}" ${visibleColumns.has(index) ? 'checked' : ''}>
                <span class="checkbox-custom"></span>
                <span class="checkbox-text">${header.textContent.trim()}</span>
            </label>
        `).join('');
    };
    
    // Apply column visibility
    const applyColumnVisibility = () => {
        headers.forEach((header, index) => {
            const cells = table.querySelectorAll(`tr td:nth-child(${index + 1}), tr th:nth-child(${index + 1})`);
            cells.forEach(cell => {
                cell.style.display = visibleColumns.has(index) ? '' : 'none';
            });
        });
        
        // Save preference
        localStorage.setItem('visibleColumns', JSON.stringify([...visibleColumns]));
    };
    
    // Open modal
    toggleBtn.addEventListener('click', () => {
        populateColumnList();
        modal.hidden = false;
    });
    
    // Close modal
    const closeModal = () => {
        modal.hidden = true;
    };
    
    closeBtn?.addEventListener('click', closeModal);
    backdrop?.addEventListener('click', closeModal);
    
    // Reset columns
    resetBtn?.addEventListener('click', () => {
        visibleColumns = new Set(defaultVisible);
        populateColumnList();
    });
    
    // Apply changes
    applyBtn?.addEventListener('click', () => {
        visibleColumns = new Set(
            Array.from(columnList.querySelectorAll('input:checked'))
                .map(input => parseInt(input.value))
        );
        applyColumnVisibility();
        closeModal();
    });
    
    // Apply initial visibility
    applyColumnVisibility();
}

// =============================================================================
// Recent Tasks
// =============================================================================

/**
 * Initialize recent tasks section
 */
function initRecentTasks() {
    const section = document.getElementById('recent-tasks-section');
    if (!section) return;
    
    const refreshBtn = document.getElementById('refresh-tasks');
    
    // Initial load
    loadRecentTasks();
    
    // Set up auto-refresh every 3 seconds
    let refreshInterval = setInterval(loadRecentTasks, 3000);
    
    // Manual refresh button
    refreshBtn?.addEventListener('click', () => {
        refreshBtn.classList.add('spinning');
        loadRecentTasks().finally(() => {
            setTimeout(() => {
                refreshBtn.classList.remove('spinning');
            }, 500);
        });
    });
    
    // Pause auto-refresh when page is not visible
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            clearInterval(refreshInterval);
        } else {
            loadRecentTasks();
            refreshInterval = setInterval(loadRecentTasks, 3000);
        }
    });
}

/**
 * Load recent tasks from API
 */
async function loadRecentTasks() {
    const listEl = document.getElementById('recent-tasks-list');
    const emptyEl = document.getElementById('tasks-empty');
    
    if (!listEl) return;
    
    try {
        const response = await fetch('/api/jobs?limit=10');
        const data = await response.json();
        
        if (!data.jobs || data.jobs.length === 0) {
            emptyEl.style.display = 'flex';
            // Remove any task cards but keep empty state
            listEl.querySelectorAll('.task-card').forEach(el => el.remove());
            return;
        }
        
        emptyEl.style.display = 'none';
        
        // Update or create task cards
        const existingCards = new Map();
        listEl.querySelectorAll('.task-card').forEach(card => {
            existingCards.set(card.dataset.jobId, card);
        });
        
        const seenJobIds = new Set();
        
        data.jobs.forEach((job, index) => {
            seenJobIds.add(job.job_id);
            
            let card = existingCards.get(job.job_id);
            if (card) {
                // Update existing card
                updateTaskCard(card, job);
            } else {
                // Create new card
                card = createTaskCard(job);
                listEl.appendChild(card);
            }
        });
        
        // Remove cards for jobs that no longer exist
        existingCards.forEach((card, jobId) => {
            if (!seenJobIds.has(jobId)) {
                card.remove();
            }
        });
        
    } catch (error) {
        console.error('Failed to load recent tasks:', error);
    }
}

/**
 * Create a task card element
 * @param {Object} job - Job data
 * @returns {HTMLElement} Task card element
 */
function createTaskCard(job) {
    const card = document.createElement('a');
    card.href = `/task/${job.job_id}`;
    card.className = `task-card task-status-${job.status}`;
    card.dataset.jobId = job.job_id;
    
    card.innerHTML = getTaskCardHTML(job);
    
    // Prevent navigation when clicking on action buttons inside the card
    card.addEventListener('click', (e) => {
        if (e.target.closest('.task-card-actions a, .task-card-actions button')) {
            e.stopPropagation();
        }
    });
    
    return card;
}

/**
 * Update an existing task card
 * @param {HTMLElement} card - Card element
 * @param {Object} job - Job data
 */
function updateTaskCard(card, job) {
    card.className = `task-card task-status-${job.status}`;
    card.href = `/task/${job.job_id}`;
    card.innerHTML = getTaskCardHTML(job);
}

/**
 * Generate HTML for a task card
 * @param {Object} job - Job data
 * @returns {string} HTML string
 */
function getTaskCardHTML(job) {
    const statusIcon = getStatusIcon(job.status);
    const statusBadgeClass = `task-badge-${job.status}`;
    const orgsText = job.organizations?.join(', ') || 'Unknown';
    const startedAt = job.started_at ? formatRelativeTime(new Date(job.started_at)) : '';
    
    let progressHTML = '';
    if (job.status === 'running' || job.status === 'pending') {
        const progressPercent = job.progress || 0;
        const processedText = job.total_repos > 0 
            ? `${job.processed_repos || 0}/${job.total_repos} repos`
            : 'Fetching...';
        
        progressHTML = `
            <div class="task-progress">
                <div class="task-progress-bar">
                    <div class="task-progress-fill" style="width: ${progressPercent}%"></div>
                </div>
                <div class="task-progress-text">
                    <span>${processedText}</span>
                    <span>${progressPercent}%</span>
                </div>
                ${job.current_repo ? `
                    <div class="task-current-repo">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                        </svg>
                        ${escapeHtml(job.current_repo)}
                    </div>
                ` : ''}
            </div>
        `;
    } else if (job.status === 'completed') {
        progressHTML = `
            <div class="task-progress">
                <div class="task-progress-bar">
                    <div class="task-progress-fill" style="width: 100%"></div>
                </div>
                <div class="task-progress-text">
                    <span>${job.result_count || 0} repositories analyzed</span>
                    <span>100%</span>
                </div>
            </div>
        `;
    } else if (job.status === 'failed') {
        progressHTML = `
            <div class="task-progress">
                <div class="task-progress-bar">
                    <div class="task-progress-fill" style="width: ${job.progress || 0}%"></div>
                </div>
                <div class="task-progress-text">
                    <span>Failed</span>
                    <span>${job.progress || 0}%</span>
                </div>
            </div>
        `;
    }
    
    let actionsHTML = '';
    if (job.status === 'completed') {
        actionsHTML = `
            <div class="task-card-actions">
                <a href="/results?job_id=${job.job_id}" class="btn btn-sm btn-primary">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                    </svg>
                    View Results
                </a>
            </div>
        `;
    }
    
    return `
        <div class="task-card-header">
            <div class="task-status-indicator">
                ${statusIcon}
            </div>
            <div class="task-info">
                <h3 class="task-title">${escapeHtml(orgsText)}</h3>
                <div class="task-meta">
                    ${startedAt ? `
                        <span class="task-meta-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/>
                                <polyline points="12 6 12 12 16 14"/>
                            </svg>
                            ${startedAt}
                        </span>
                    ` : ''}
                    <span class="task-badge ${statusBadgeClass}">${job.status}</span>
                </div>
            </div>
            ${actionsHTML}
        </div>
        ${progressHTML}
    `;
}

/**
 * Get status icon SVG
 * @param {string} status - Job status
 * @returns {string} SVG HTML
 */
function getStatusIcon(status) {
    switch (status) {
        case 'running':
            return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>`;
        case 'completed':
            return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"/>
            </svg>`;
        case 'failed':
            return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>`;
        case 'pending':
        default:
            return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
            </svg>`;
    }
}

/**
 * Format a date as relative time
 * @param {Date} date - Date to format
 * @returns {string} Relative time string
 */
function formatRelativeTime(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    
    if (diffSec < 60) {
        return 'Just now';
    } else if (diffMin < 60) {
        return `${diffMin}m ago`;
    } else if (diffHour < 24) {
        return `${diffHour}h ago`;
    } else if (diffDay < 7) {
        return `${diffDay}d ago`;
    } else {
        return date.toLocaleDateString();
    }
}

// =============================================================================
// Initialize on DOM Ready
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize based on page
    if (document.getElementById('analysis-form')) {
        initAnalysisForm();
    }
    
    if (document.getElementById('recent-tasks-section')) {
        initRecentTasks();
    }
    
    if (document.getElementById('results-table')) {
        initResultsPage();
    }
});
