# CI/CD Quick Setup Guide

This guide will help you activate and configure the GitHub Actions CI/CD pipeline for the AI Trading Race project.

## ✅ Prerequisites

- Repository hosted on GitHub
- Admin access to the repository
- GitHub CLI installed (optional, for automation)

## 🚀 Setup Steps

### 1. Push CI/CD Configuration to GitHub

All workflow files are already created in `.github/workflows/`. Simply commit and push:

```bash
git add .github/
git commit -m "ci: add GitHub Actions workflows for CI/CD"
git push origin phase-8
```

### 2. Enable GitHub Actions

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Actions** → **General**
3. Under "Actions permissions", select:
   - ✅ **Allow all actions and reusable workflows**
4. Click **Save**

### 3. Verify Workflows Are Running

After pushing, workflows should automatically trigger:

```bash
# Check workflow runs
gh run list --limit 10

# Watch a specific workflow
gh run watch
```

Or visit: `https://github.com/diegoaquinoh/ai-trading-race/actions`

### 4. Set Up Branch Protection (Recommended)

Protect the `main` branch to require CI checks before merging:

#### Via GitHub UI:
1. Go to **Settings** → **Branches**
2. Click **Add rule** for `main`
3. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
   - Select: `Backend CI`, `Frontend CI`, `Functions CI`, `ML Service CI`
   - ✅ Require branches to be up to date before merging
4. Click **Create**

#### Via GitHub CLI:
```bash
gh api repos/diegoaquinoh/ai-trading-race/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_status_checks[contexts][]=backend \
  --field required_status_checks[contexts][]=frontend \
  --field required_status_checks[contexts][]=functions \
  --field required_status_checks[contexts][]=ml-service \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field enforce_admins=true
```

### 5. Test the CI Pipeline

Create a test pull request:

```bash
# Create a feature branch
git checkout -b test-ci-pipeline

# Make a small change
echo "# CI Test" >> README.md
git add README.md
git commit -m "test: verify CI pipeline"
git push origin test-ci-pipeline

# Create PR
gh pr create --title "test: verify CI pipeline works" --body "Testing automated CI workflows"
```

Check that all workflows run successfully in the PR.

### 6. Add CI Status Badges (Optional)

Add to your main `README.md`:

```markdown
## CI/CD Status

![Backend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Backend%20CI%2FCD/badge.svg?branch=main)
![Frontend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Frontend%20CI%2FCD/badge.svg?branch=main)
![Functions CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Azure%20Functions%20CI%2FCD/badge.svg?branch=main)
![ML Service CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/ML%20Service%20CI%2FCD/badge.svg?branch=main)
```

## 🔧 Configuration Details

### Workflow Triggers

All workflows are configured to run on:
- **Push** to `main`, `develop`, or `phase-*` branches
- **Pull requests** to `main` or `develop`
- **Manual trigger** via GitHub UI or CLI

### Paths Filtering

Workflows only run when relevant files change:
- `backend.yml` → `.cs`, `.csproj`, solution files
- `frontend.yml` → `ai-trading-race-web/**`
- `functions.yml` → `AiTradingRace.Functions/**`
- `ml-service.yml` → `ai-trading-race-ml/**`

### Artifacts

All workflows produce artifacts retained for **30 days**:
- `web-api` - Backend API build
- `azure-functions` - Functions build
- `frontend-build` - React production build
- Docker images cached in GitHub Actions

## 🐛 Troubleshooting

### Workflows Not Running

1. Check that `.github/workflows/` files are pushed to the remote
2. Verify Actions are enabled in repository settings
3. Check the Actions tab for any errors

### Build Failures

#### Backend (.NET)
```bash
# Run locally first
cd AiTradingRace.Web
dotnet restore
dotnet build --configuration Release
dotnet test
```

#### Frontend (React)
```bash
# Run locally first
cd ai-trading-race-web
npm ci
npm run lint
npm run build
```

#### ML Service (Python)
```bash
# Run locally first
cd ai-trading-race-ml
pip install -r requirements.txt
pytest tests/
black --check app/
```

### Cache Issues

Clear GitHub Actions cache:
1. Go to **Actions** → **Caches**
2. Delete old caches
3. Re-run failed workflows

## 📊 Monitoring

### View Workflow Status

```bash
# List recent runs
gh run list --workflow=backend.yml --limit 5

# View run details
gh run view <run-id>

# Re-run a failed workflow
gh run rerun <run-id>
```

### Set Up Notifications

1. Go to **Settings** → **Notifications**
2. Enable:
   - ✅ Actions workflows
   - ✅ Pull requests
   - ✅ Pushes

## 🎯 Next Steps

Once CI/CD is working:

1. ✅ All team members should see workflows running on their PRs
2. ✅ Failed checks should block merging to `main`
3. ✅ Artifacts are available for manual deployment
4. 🔄 **Future**: Configure Azure secrets for automated deployment

## 📚 Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [CI/CD Best Practices](https://docs.github.com/en/actions/guides)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)

## ✅ Success Criteria

- [ ] All workflows appear in the Actions tab
- [ ] Workflows run automatically on push/PR
- [ ] All jobs complete successfully (green checkmarks)
- [ ] Artifacts are generated and accessible
- [ ] Branch protection rules are enforced
- [ ] PR template and issue templates work

---

**Questions?** Check the [CI/CD README](.github/README.md) for detailed documentation.
