# CI/CD Activation Checklist

Use this checklist to verify your CI/CD pipeline is fully functional.

## 📋 Pre-Activation Checklist

- [ ] All `.github/` files are committed to the repository
- [ ] You have admin access to the GitHub repository
- [ ] GitHub Actions are enabled in repository settings
- [ ] You're on the correct branch (`phase-8`)

## 🚀 Activation Steps

### 1. Push Configuration to GitHub

```bash
# Verify files are staged
git status

# Commit if needed
git add .github/
git commit -m "ci: add GitHub Actions CI/CD pipeline"

# Push to GitHub
git push origin phase-8
```

- [ ] Files pushed successfully
- [ ] No errors in git push

### 2. Verify Workflows Appear

Visit: `https://github.com/diegoaquinoh/ai-trading-race/actions`

- [ ] "Actions" tab is visible
- [ ] Workflows list shows 7 workflows:
  - [ ] Backend CI/CD
  - [ ] Azure Functions CI/CD
  - [ ] Frontend CI/CD
  - [ ] ML Service CI/CD
  - [ ] Pull Request Checks
  - [ ] CI - Full Pipeline
  - [ ] Validate Workflows

### 3. Trigger Initial Workflow Runs

The push should have triggered workflows automatically.

Check status:
```bash
gh run list --limit 10
```

- [ ] At least one workflow run appears
- [ ] Workflow runs show "In progress" or "Completed"

### 4. Verify Individual Workflows

#### Backend Workflow
```bash
gh run list --workflow=backend.yml --limit 3
```

Expected jobs:
- [ ] Build and Test .NET Backend
- [ ] Code Quality Checks

#### Frontend Workflow
```bash
gh run list --workflow=frontend.yml --limit 3
```

Expected jobs:
- [ ] Build and Test React Frontend
- [ ] Bundle Size Analysis

#### Functions Workflow
```bash
gh run list --workflow=functions.yml --limit 3
```

Expected jobs:
- [ ] Build Azure Functions
- [ ] Validate Functions Configuration

#### ML Service Workflow
```bash
gh run list --workflow=ml-service.yml --limit 3
```

Expected jobs:
- [ ] Lint and Test Python ML Service
- [ ] Build Docker Image
- [ ] Security Vulnerability Scan

### 5. Check Artifacts

After workflows complete successfully:

```bash
# List artifacts for latest run
gh run view --log-failed
```

- [ ] `web-api` artifact created (~50 MB)
- [ ] `azure-functions` artifact created (~60 MB)
- [ ] `frontend-build` artifact created (~5 MB)
- [ ] Docker image cached in GitHub Actions

### 6. Test PR Validation

Create a test PR:
```bash
# Create feature branch
git checkout -b test/ci-validation

# Make a small change
echo "# CI Test" >> README.md
git add README.md
git commit -m "test: verify CI pipeline functionality"
git push origin test/ci-validation

# Create PR
gh pr create \
  --title "test: verify CI pipeline works correctly" \
  --body "Testing the automated CI/CD pipeline setup"
```

- [ ] PR created successfully
- [ ] PR checks start automatically
- [ ] PR template appears in description
- [ ] "Pull Request Checks" workflow runs
- [ ] All relevant CI workflows run (based on changed files)

### 7. Verify PR Checks

In the PR you just created:

- [ ] PR title validation passes (Conventional Commits format)
- [ ] PR size analysis shows stats
- [ ] Merge conflict check passes
- [ ] TODO/FIXME check passes
- [ ] Status checks appear at bottom of PR
- [ ] "Merge" button is blocked until checks pass (if branch protection enabled)

### 8. Enable Branch Protection (Optional but Recommended)

```bash
# Protect main branch
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

Or via GitHub UI: Settings → Branches → Add rule for `main`

- [ ] Branch protection rule created for `main`
- [ ] Required status checks selected
- [ ] "Require pull request reviews before merging" enabled
- [ ] Changes saved

### 9. Test Issue Templates

Create a test issue:
```bash
gh issue create --template bug_report.yml
```

- [ ] Bug report template loads correctly
- [ ] Feature request template available
- [ ] All fields render properly

### 10. Verify Code Owners

- [ ] `.github/CODEOWNERS` file exists
- [ ] Contains your GitHub username
- [ ] Automatic review requests will trigger on PRs

## 🧪 Functionality Tests

### Test 1: Path Filtering
Make a change only to frontend code:
```bash
git checkout -b test/path-filter
echo "// test" >> ai-trading-race-web/src/App.tsx
git commit -am "test: path filtering"
git push origin test/path-filter
```

Expected behavior:
- [ ] Only frontend workflow runs
- [ ] Backend workflow is skipped
- [ ] Functions workflow is skipped
- [ ] ML Service workflow is skipped

### Test 2: Full CI Pipeline
Make changes to multiple components:
```bash
git checkout -b test/full-pipeline
echo "// test" >> AiTradingRace.Web/Program.cs
echo "// test" >> ai-trading-race-web/src/App.tsx
git commit -am "test: full pipeline"
git push origin test/full-pipeline
```

Expected behavior:
- [ ] Backend workflow runs
- [ ] Frontend workflow runs
- [ ] Functions workflow may run (if affected)
- [ ] All workflows complete successfully

### Test 3: Failing Build
Introduce a syntax error:
```bash
git checkout -b test/failing-build
echo "SYNTAX ERROR" >> AiTradingRace.Web/Program.cs
git commit -am "test: failing build"
git push origin test/failing-build
```

Expected behavior:
- [ ] Backend workflow runs
- [ ] Build fails with clear error message
- [ ] Workflow status shows ❌
- [ ] PR cannot be merged (if branch protection enabled)

Then fix it:
```bash
git revert HEAD
git push origin test/failing-build
```

- [ ] New workflow run starts automatically
- [ ] Build passes ✅
- [ ] PR becomes mergeable

### Test 4: Artifacts Download
After a successful workflow run:
```bash
# Get latest run ID
RUN_ID=$(gh run list --workflow=backend.yml --limit 1 --json databaseId --jq '.[0].databaseId')

# Download artifact
gh run download $RUN_ID --name web-api --dir ./downloaded-artifacts
```

- [ ] Artifact downloads successfully
- [ ] Contains expected files (published .NET application)

## 📊 Final Verification

### Check Workflow Status Page
Visit: `https://github.com/diegoaquinoh/ai-trading-race/actions`

- [ ] All workflows show green checkmarks (most recent run)
- [ ] No failed workflows in last 5 runs
- [ ] Workflow run history is visible
- [ ] Each workflow has correct triggers listed

### Check Branch Protection
Visit: `https://github.com/diegoaquinoh/ai-trading-race/settings/branches`

- [ ] `main` branch shows protection rules
- [ ] Status checks are required
- [ ] PR reviews are required (optional)
- [ ] Settings match your requirements

### Check Notifications
- [ ] You received GitHub notifications for workflow runs
- [ ] Email notifications configured (optional)
- [ ] Slack/Discord webhooks configured (optional)

## ✅ Success Criteria

Mark complete when:
- [ ] All 7 workflows run successfully on push to `phase-8`
- [ ] PR checks validate title format and other rules
- [ ] Artifacts are generated and downloadable
- [ ] Path filtering works correctly
- [ ] Branch protection prevents merging with failed checks
- [ ] Documentation is clear and accessible
- [ ] Issue and PR templates work as expected

## 🎉 Completion

If all checks pass:

```bash
# Merge test branch to main (via PR)
gh pr merge test/ci-validation --squash --delete-branch

# Or close test PRs
gh pr close test/ci-validation --delete-branch
```

**Congratulations! Your CI/CD pipeline is fully operational! 🚀**

## 🐛 Troubleshooting

If something doesn't work, check:

1. **Workflows not appearing**: 
   - Verify `.github/workflows/` pushed to remote
   - Check Actions are enabled in settings

2. **Workflows not running**:
   - Check trigger conditions (branches, paths)
   - Verify workflow YAML syntax

3. **Build failures**:
   - Run builds locally first
   - Check error messages in workflow logs
   - Verify dependencies are correct

4. **Artifacts not created**:
   - Check artifact upload step succeeded
   - Verify paths are correct
   - Check artifact retention settings

See `.github/README.md` for detailed troubleshooting.

---

**Last Updated**: January 20, 2026  
**Phase**: 8 - CI/CD Setup  
**Sprint**: 8.4 ✅
