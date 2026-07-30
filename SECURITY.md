# Security Policy

## Reporting a Vulnerability

The Luminari Sage team takes security seriously. We appreciate your efforts to responsibly disclose your findings.

### How to Report

If you discover a security vulnerability, please report it by:

- **Email**: security@luminarimud.com
- **Expected Response Time**: Within 48 hours
- **Disclosure Policy**: Coordinated disclosure (90 days)

### What to Include

Please provide:

- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Suggested remediation (if available)

**Please do not:**

- Publicly disclose the vulnerability before it has been addressed
- Access or modify data that doesn't belong to you
- Perform denial-of-service attacks
- Send large volumes of automated requests

## Supported Versions

| Version | Security Support         |
| ------- | ------------------------ |
| 0.4.0+  | ✅ Full security support |
| < 0.4.0 | ❌ No security patches   |

## Security Measures

Luminari Sage implements multiple layers of security:

### 1. Credential Management

- ✅ **No tracked credential values** - Development uses a restricted `.env`;
  production mounts credentials from owner-only Compose secret files
- ✅ **Credential validation** - Missing database credentials are rejected before connecting
- ✅ **No default passwords** - Eliminates weak fallback configurations
- ✅ **Comprehensive .gitignore** - Prevents common local secret files from being tracked

### 2. Automated Security Scanning

- ✅ **Pre-commit hooks** - Gitleaks blocks commits containing secrets
- ✅ **CI/CD scanning** - GitHub Actions runs security scans on every PR
- ✅ **Dependency scanning** - pip-audit checks for vulnerable packages
- ✅ **Docker image scanning** - Trivy scans for container vulnerabilities
- ✅ **Code security linting** - Bandit detects Python security issues

### 3. Access Control

- ✅ **Multi-key authentication** - Separate API keys for backend, MCP operations, MCP backend
- ✅ **Path-based authorization** - Different endpoints require different key types
- ✅ **Non-root containers** - Docker runs as unprivileged user (uid 1013)
- ✅ **SSH host verification** - Proper known_hosts configuration in CI/CD

### 4. Data Protection

- ✅ **Safe query construction** - Values are parameterized and dynamic identifiers validated
- ✅ **Input validation** - Pydantic models validate all API inputs
- ✅ **Credential redaction** - Known credential forms are removed from logs and public errors
- ✅ **Secure defaults** - Restrictive CORS, host validation, and browser headers

### 5. Infrastructure Security

- ✅ **Required password syntax** - Docker Compose enforces credential presence
- ✅ **Health checks** - Services monitored for availability
- ✅ **Resource limits** - CPU and memory caps prevent resource exhaustion
- ✅ **Network isolation** - Services communicate via isolated Docker network

## Security Audit History

### 2026-07-30: Credential Exposure and Runtime Hardening

**Scope**: Tracked files, full Git history, ignored local artifacts, application
error paths, browser UI, deployment workflow, dependencies, and container
networking.

**Material finding**: A historical lore draft contained plaintext shared-account
credentials. The file was removed and repository history was sanitized. Because
history rewriting cannot invalidate a credential, the affected account owners
must rotate the credentials and invalidate active sessions independently.

**Key improvements**:

- Expanded Gitleaks rules to detect low-entropy credential tables
- Replaced licensed CI-only secret scanning with a checksum-verified CLI scan
- Removed browser credential persistence and escaped server-controlled UI content
- Redacted public exceptions and credential-shaped log content
- Restricted production database, graph, API, and MCP ports to loopback
- Reworked deployment secret transport to avoid shell sourcing and command arguments
- Removed unused vulnerable dependencies

This audit is evidence of a point-in-time review, not a compliance certification.

### 2025-11-16: Initial Security Audit

The initial audit introduced environment-based configuration, fail-fast
credential validation, pre-commit scanning, and CI security checks. Later review
found gaps in those checks; the 2026 audit above supersedes its security-grade
claims.

## Security Best Practices for Contributors

### Before Committing Code

1. **Install pre-commit hooks**:

   ```bash
   pip install pre-commit
   pre-commit install
   ```

2. **Run security checks locally**:

   ```bash
   # Check for secrets
   pre-commit run gitleaks --all-files

   # Check for vulnerabilities
   pip-audit -r requirements.txt

   # Lint for security issues
   bandit -r src/
   ```

3. **Never commit**:
   - API keys, passwords, or tokens
   - `.env` files (use `.env.example` instead)
   - Private keys, certificates, or credentials
   - Connection strings with embedded passwords
   - Test data containing real credentials

### Environment Variables

Development secrets are configured through environment variables or a
mode-`0600` `.env` file. Production deployment converts GitHub Actions secrets
to owner-only Compose secret files and exposes only their file paths to
containers:

**Required production secrets** (see `.env.example`):

- `SAGE_API_KEY` - Backend API authentication (64-char hex)
- `POSTGRES_PASSWORD` - PostgreSQL password (16+ chars)
- `NEO4J_PASSWORD` - Neo4j password (16+ chars)
- `OPENAI_API_KEY` - OpenAI API key for embeddings/LLM
- `SAGE_MCP_KEY` - MCP operations authentication
- `SAGE_MCP_BACKEND_KEY` - MCP backend access authentication

**Optional secrets**:

- `LANGSMITH_API_KEY` - LangSmith tracing; tracing is disabled by default

### Generating Secure Secrets

```bash
# Generate 64-character hex API key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate 32-character URL-safe token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate strong password (32 characters)
python3 -c "import secrets; import string; chars = string.ascii_letters + string.digits + string.punctuation; print(''.join(secrets.choice(chars) for _ in range(32)))"
```

### Code Review Checklist

Security items to verify in pull requests:

- [ ] No hardcoded credentials or API keys
- [ ] All secrets loaded from environment variables
- [ ] No default/fallback credentials in code
- [ ] Database queries use parameterization (no string concatenation)
- [ ] Input validation with Pydantic models
- [ ] No sensitive data in error messages or logs
- [ ] Pre-commit hooks passing (including Gitleaks)
- [ ] No new dependencies with known vulnerabilities

## Credential Rotation Policy

**Frequency**: Every 90 days (recommended)

**Process**:

1. Generate new credential using secure method (see above)
2. Update `.env` file with new value
3. Restart affected services:
   ```bash
   docker compose restart api
   ```
4. Test authentication with new credential
5. Verify old credential is rejected
6. Update any external clients/services
7. Document rotation in change log

**Emergency Rotation**: Immediately rotate credentials if:

- Credential accidentally committed to git
- Credential exposed in logs or error messages
- Unauthorized access detected
- Team member with access leaves project

## Incident Response

If you discover or experience a security incident:

1. **Immediately** rotate any compromised credentials
2. **Report** to security@luminarimud.com with full details
3. **Preserve** logs and evidence for investigation
4. **Document** timeline, impact, and remediation steps
5. **Review** and update security measures to prevent recurrence

## Security Resources

### Tools Used

- **Gitleaks**: Git secret scanner - https://github.com/gitleaks/gitleaks
- **pip-audit**: Python dependency vulnerability scanner - https://pypi.org/project/pip-audit/
- **Bandit**: Python code security linter - https://bandit.readthedocs.io/
- **Trivy**: Container vulnerability scanner - https://trivy.dev/
- **pre-commit**: Git hook framework - https://pre-commit.com/

### Standards & Guidelines

- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **CWE-798**: Use of Hard-coded Credentials - https://cwe.mitre.org/data/definitions/798.html
- **NIST SP 800-53**: Security Controls - https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
- **Docker Security**: https://docs.docker.com/engine/security/

### Contact

- **Security Issues**: security@luminarimud.com
- **General Support**: GitHub Issues

---

**Last Updated**: 2026-07-30
**Next Review**: 2026-10-30
