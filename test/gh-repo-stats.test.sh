#!/usr/bin/env bash
# Test file for gh-repo-stats

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Test helper functions
pass() {
  echo "✓ $1"
  ((TESTS_PASSED++))
}

fail() {
  echo "✗ $1"
  ((TESTS_FAILED++))
}

# Test: Script file exists
test_script_exists() {
  if [[ -f "$ROOT_DIR/gh-repo-stats" ]]; then
    pass "gh-repo-stats script exists"
  else
    fail "gh-repo-stats script exists"
  fi
}

# Test: Script is executable
test_script_executable() {
  if [[ -x "$ROOT_DIR/gh-repo-stats" ]]; then
    pass "gh-repo-stats script is executable"
  else
    fail "gh-repo-stats script is executable"
  fi
}

# Test: Script has valid bash shebang
test_script_shebang() {
  if head -1 "$ROOT_DIR/gh-repo-stats" | grep -q "#!/usr/bin/env bash"; then
    pass "gh-repo-stats has valid bash shebang"
  else
    fail "gh-repo-stats has valid bash shebang"
  fi
}

# Test: --help flag exits with 0
test_help_flag_exits_zero() {
  if "$ROOT_DIR/gh-repo-stats" --help &> /dev/null; then
    pass "--help flag exits with 0"
  else
    fail "--help flag exits with 0"
  fi
}

# Test: Fetch stats for a repository
test_fetch_stats_for_repo() {
    if "$ROOT_DIR/gh-repo-stats" -u "https://github.com/stedolan/jq" | grep -q "Statistics for"; then
        pass "Fetch stats for a repository"
    else
        fail "Fetch stats for a repository"
    fi
}

# Run all tests
main() {
  echo "Running gh-repo-stats tests..."
  echo ""

  test_script_exists
  test_script_executable
  test_script_shebang
  test_help_flag_exits_zero
  test_fetch_stats_for_repo

  echo ""
  echo "Results: $TESTS_PASSED passed, $TESTS_FAILED failed"

  if [[ $TESTS_FAILED -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
