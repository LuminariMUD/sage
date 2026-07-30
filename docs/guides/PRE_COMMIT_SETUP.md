# Pre-Commit Hooks Setup Guide

This guide walks you through installing and configuring the pre-commit security hooks for Luminari Sage.

---

## Why Pre-Commit Hooks?

Pre-commit hooks are **automated checks** that run before each git commit to:

- ✅ **Block commits containing secrets** (API keys, passwords, tokens)
- ✅ **Format code automatically** (Black, isort for Python)
- ✅ **Catch common errors** (trailing whitespace, large files, private keys)
- ✅ **Enforce code quality** (flake8 linting)
- ✅ **Validate configurations** (YAML syntax, merge conflicts)

**Critical for security**: Prevents accidental credential commits that would require emergency rotation.

---

## Quick Setup (5 minutes)

### Step 1: Install Gitleaks

**macOS**:

```bash
brew install gitleaks
```

**Linux (Ubuntu/Debian)**:

```bash
wget https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz
tar -xzf gitleaks_8.18.4_linux_x64.tar.gz
sudo mv gitleaks /usr/local/bin/
chmod +x /usr/local/bin/gitleaks
rm gitleaks_8.18.4_linux_x64.tar.gz
```

**Verify installation**:

```bash
gitleaks version
# Expected output: 8.18.4 (or similar)
```

### Step 2: Install Pre-Commit Framework

```bash
pip install pre-commit
```

**Verify installation**:

```bash
pre-commit --version
# Expected output: pre-commit 3.x.x
```

### Step 3: Install Git Hooks

```bash
# Navigate to project root
cd /path/to/sage

# Install hooks into .git/hooks/
pre-commit install

# Expected output:
# pre-commit installed at .git/hooks/pre-commit
```

### Step 4: Test Installation

**Option A: Run on All Files** (recommended first time):

```bash
pre-commit run --all-files
```

This will:

- Download and install all hook dependencies
- Run all checks on your entire codebase
- May take 2-3 minutes on first run (subsequent runs are fast)

**Option B: Test with a Fake Secret**:

```bash
# Create an ignored, disposable test value at runtime
printf 'SAGE_API_KEY=%s\n' "$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > test_secret.txt

# Try to commit it
git add test_secret.txt
git commit -m "Test: Should be blocked by Gitleaks"

# Expected: Gitleaks blocks the commit with error message
# Finding:    SAGE_API_KEY=<generated-64-character-hex-value>
# Commit blocked to prevent credential leakage

# Clean up
git reset HEAD test_secret.txt
rm test_secret.txt
```

---

## What Happens When You Commit?

### Normal Workflow (No Issues)

```bash
git add file.py
git commit -m "feat: add new feature"

# Pre-commit runs automatically:
# - Gitleaks scans for secrets ✅
# - Black formats Python code ✅
# - isort sorts imports ✅
# - flake8 lints code ✅
# - YAML validation ✅
# - ... (other hooks) ✅

# All checks pass → Commit succeeds
[main abc1234] feat: add new feature
```

### When Secrets Detected 🚨

```bash
git add file.py
git commit -m "feat: add API integration"

# Pre-commit runs:
# - Gitleaks scans for secrets ❌

Gitleaks........................................Failed
- hook id: gitleaks
- exit code: 1

Finding:    API_KEY="example-redacted-key"
Secret:     OpenAI API Key
Line:       42
Commit:     BLOCKED

# Commit is REJECTED - secret not committed
# Fix: Remove the secret, use environment variable instead
```

### When Code Formatting Needed 🔧

```bash
git add messy_file.py
git commit -m "feat: add feature"

# Pre-commit runs:
# - Black formats code ⚠️  (auto-fixed)
# - isort sorts imports ⚠️  (auto-fixed)

black...........................Failed
- hook id: black
- files were modified by this hook

isort...........................Failed
- hook id: isort
- files were modified by this hook

# Files were automatically formatted!
# Run git add and commit again:

git add messy_file.py
git commit -m "feat: add feature"

# All checks pass → Commit succeeds
[main def5678] feat: add feature
```

---

## Configuration Files

### `.pre-commit-config.yaml`

**Location**: Project root

**Purpose**: Defines which hooks to run

**Installed Hooks**:

1. **Gitleaks** - Secret scanner (most important!)
2. **trailing-whitespace** - Removes trailing spaces
3. **end-of-file-fixer** - Ensures newline at end
4. **check-yaml** - Validates YAML syntax
5. **check-added-large-files** - Blocks files >1MB
6. **detect-private-key** - Detects SSH/TLS keys
7. **check-merge-conflict** - Detects merge markers
8. **check-case-conflict** - Detects case conflicts
9. **mixed-line-ending** - Detects mixed endings
10. **black** - Python code formatter
11. **isort** - Python import sorter
12. **flake8** - Python linter
13. **prettier** - Markdown/YAML formatter

### `.gitleaks.toml`

**Location**: Project root

**Purpose**: Configures Gitleaks secret detection

**Custom Rules** (8 total):

- `sage-api-key` - 64-char hex Sage keys
- `postgres-password` - Database passwords
- `neo4j-password` - Graph DB passwords
- `jwt-secret` - JWT signing keys
- `openai-api-key` - OpenAI API keys
- `langsmith-api-key` - LangSmith keys
- `database-url` - Connection strings with creds
- Plus all default Gitleaks rules

**Allowlist** (prevents false positives):

- Paths: `.env.example`, `docs/`, `tests/fixtures/`
- Patterns: `test_dummy_key`, `PLACEHOLDER`, `example.*password`

---

## Common Scenarios

### Scenario 1: Urgent Hotfix (Bypass Hooks)

⚠️ **Use with extreme caution and explicit approval only**

```bash
# Emergency bypass (requires follow-up commit)
git commit --no-verify -m "hotfix: critical bug (hooks bypassed with approval)"

# IMMEDIATELY create follow-up commit that passes hooks
git commit -m "chore: fix code quality issues from hotfix"
```

**Best Practice**: Never bypass unless absolutely necessary. If you must, document why in commit message and create follow-up commit.

### Scenario 2: Update Hook Versions

```bash
# Update to latest hook versions
pre-commit autoupdate

# Re-run on all files
pre-commit run --all-files

# Commit the updated config
git add .pre-commit-config.yaml
git commit -m "chore: update pre-commit hook versions"
```

### Scenario 3: Skip Specific Hook

```bash
# Skip only Black formatting (not recommended)
SKIP=black git commit -m "feat: add feature"

# Skip multiple hooks
SKIP=black,isort git commit -m "feat: add feature"
```

**Warning**: Do not skip Gitleaks on a commit. Resolve or narrowly document a
verified false positive first.

### Scenario 4: Run Specific Hook Only

```bash
# Run only Gitleaks
pre-commit run gitleaks --all-files

# Run only Black
pre-commit run black --all-files

# Run only on staged files
pre-commit run gitleaks
```

### Scenario 5: False Positive in Gitleaks

If Gitleaks incorrectly flags something as a secret:

**Option A: Add an exact, rule-scoped allowlist in `.gitleaks.toml`**:

```toml
[[rules.allowlists]]
description = "One reviewed placeholder used by this rule"
regexTarget = "secret"
regexes = [
    '''^<documented-placeholder>$'''
]
```

**Option B: Exclude one verified fixture path**:

```toml
[allowlist]
paths = [
    # Keep this exact; never exclude a whole source or documentation tree.
    '''^tests/fixtures/non_secret_example\.txt$'''
]
```

**Option C: Replace realistic credential-shaped test data**:

```python
EXAMPLE_VALUE = "<placeholder>"
```

Do not suppress a finding until the value has been independently confirmed as
non-sensitive. Never use an inline suppression on a live or realistic key.

---

## Troubleshooting

### Issue: "gitleaks: command not found"

**Cause**: Gitleaks not installed or not in PATH

**Fix**:

```bash
# Verify installation
which gitleaks

# If not found, reinstall (see Step 1 above)
```

### Issue: "pre-commit: command not found"

**Cause**: Pre-commit framework not installed

**Fix**:

```bash
pip install pre-commit
# or
pip3 install pre-commit
```

### Issue: Hooks not running on commit

**Cause**: Hooks not installed in .git/hooks/

**Fix**:

```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install

# Verify
ls -la .git/hooks/pre-commit
```

### Issue: Hooks run too slowly

**Cause**: Running on large files or entire history

**Fix 1**: Skip large files (already configured in .gitleaks.toml)

```toml
[extend]
maxTargetMegabytes = 10  # Skip files >10MB
```

**Fix 2**: Run on staged files only (default behavior)

```bash
# Fast: only staged files
git commit

# Slow: all files
pre-commit run --all-files
```

### Issue: Black and isort conflict

**Cause**: Incompatible configurations

**Fix**: Already configured in `.pre-commit-config.yaml`:

```yaml
- id: isort
  args: ["--profile", "black"] # Makes isort compatible with Black
```

### Issue: YAML validation fails on docker-compose

**Cause**: Docker Compose uses custom YAML tags

**Fix**: Already configured in `.pre-commit-config.yaml`:

```yaml
- id: check-yaml
  args: ["--unsafe"] # Allow custom tags
```

---

## Maintenance

### Weekly/Monthly

```bash
# Update hook versions
pre-commit autoupdate

# Re-run on all files to catch any new issues
pre-commit run --all-files
```

### Quarterly

```bash
# Update Gitleaks
brew upgrade gitleaks  # macOS
# or download latest from GitHub for Linux

# Review .gitleaks.toml allowlist
# - Remove obsolete patterns
# - Add new patterns for false positives
# - Update rule configurations

# Test hooks still work
pre-commit run --all-files
```

### When Joining New Team Members

Send them this guide and have them:

1. Install Gitleaks
2. Install pre-commit framework
3. Run `pre-commit install`
4. Test with `pre-commit run --all-files`

---

## CI/CD Integration

**Good news**: CI/CD security workflow is already configured in `.github/workflows/security-scan.yml`

This means:

- Every PR runs Gitleaks automatically
- PRs are blocked if secrets detected
- No local bypass circumvents security
- Team-wide enforcement

**To verify**:

```bash
# Check workflow file exists
cat .github/workflows/security-scan.yml

# Trigger manually (requires GitHub CLI)
gh workflow run security-scan.yml
```

---

## Best Practices

### ✅ DO

- **Install hooks immediately** after cloning repo
- **Run `pre-commit run --all-files`** periodically
- **Update hooks monthly** with `pre-commit autoupdate`
- **Test hooks work** by committing a test secret
- **Report false positives** to maintainers
- **Keep .gitleaks.toml updated** with new secret types

### ❌ DON'T

- **Never commit with `--no-verify`** except emergencies
- **Never disable Gitleaks** in .pre-commit-config.yaml
- **Never add real secrets to allowlist**
- **Never skip pre-commit installation**
- **Never ignore hook failures** without investigation
- **Never commit `.env` files** (use `.env.example`)

---

## Quick Reference

### Commands

```bash
# Install hooks
pre-commit install

# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run gitleaks --all-files

# Update hook versions
pre-commit autoupdate

# Uninstall hooks
pre-commit uninstall

# Bypass hooks (emergency only)
git commit --no-verify -m "message"

# Skip specific hook
SKIP=black git commit -m "message"
```

### Files

- `.pre-commit-config.yaml` - Hook configuration
- `.gitleaks.toml` - Gitleaks rules and allowlist
- `.git/hooks/pre-commit` - Installed hook script
- `.github/workflows/security-scan.yml` - CI/CD security

### Resources

- **Gitleaks**: https://github.com/gitleaks/gitleaks
- **Pre-commit**: https://pre-commit.com/
- **Project Security**: [SECURITY.md](../../SECURITY.md)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)

---

## Help

**Issues with hooks**: Open GitHub issue with `[pre-commit]` tag
**Security questions**: See [SECURITY.md](../../SECURITY.md)
**General questions**: Open GitHub Discussion

---

**Last Updated**: 2025-11-16
**Version**: 1.0
**Status**: Production Ready
