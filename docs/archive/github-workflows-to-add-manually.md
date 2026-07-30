# GitHub Actions Workflows

These workflow files need to be added manually to the repository due to GitHub's security restrictions on workflow updates via API.

## Instructions

1. Go to your GitHub repository
2. Navigate to `.github/workflows/`
3. Create the following files manually:

### File 1: `.github/workflows/ci-cd.yml`

Copy the contents from the file `.github/workflows/ci-cd.yml` in this directory.

### File 2: `.github/workflows/deploy.yml`

Copy the contents from the file `.github/workflows/deploy.yml` in this directory.

## Required Secrets

Add these secrets in your GitHub repository settings (Settings → Secrets and variables → Actions):

### For Staging Deployment:
- `STAGING_HOST`: Your staging server hostname/IP
- `STAGING_USER`: SSH username for staging server
- `STAGING_SSH_KEY`: Private SSH key for staging server

### For Production Deployment:
- `PROD_HOST`: Your production server hostname/IP
- `PROD_USER`: SSH username for production server
- `PROD_SSH_KEY`: Private SSH key for production server
- `PROD_API_URL`: Production API URL for smoke tests
- `STAGING_API_URL`: Staging API URL for smoke tests

### Optional:
- `SLACK_WEBHOOK`: Slack webhook URL for deployment notifications
- `GRAFANA_PASSWORD`: Password for Grafana monitoring

## Workflow Triggers

- **CI/CD Pipeline**: Runs on push to main/develop branches and pull requests
- **Deployment**: Manual trigger or automatic on push to main branch

The workflows will automatically:
1. Run tests with PostgreSQL and Neo4j services
2. Build Docker images
3. Push to GitHub Container Registry
4. Deploy to staging/production environments
5. Run smoke tests