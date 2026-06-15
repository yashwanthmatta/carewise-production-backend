# CareWise Backend GitHub Upload Steps

## 1. Open This Folder

```bash
cd /Users/yashwanthmatta/Documents/Codex/2026-06-14/okay-i-want-to-build-a/outputs/carewise-production-backend
```

## 2. Confirm Checks Pass

```bash
python3 tests/static_readiness_check.py
```

## 3. Create Local Git Repo

```bash
git init
git add .
git status
git commit -m "Prepare CareWise production backend"
```

## 4. Create GitHub Repo

On GitHub, create a new empty repository named:

```text
carewise-production-backend
```

Do not add a README, .gitignore, or license on GitHub because this folder already has files.

## 5. Connect and Push

Replace `YOUR-GITHUB-USERNAME` with your GitHub username:

```bash
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-USERNAME/carewise-production-backend.git
git push -u origin main
```

## 6. Deploy on Render

Use:

```text
deploy/render/render.yaml
```

Then generate production secrets:

```bash
python3 scripts/generate_secrets.py
```

Put those values into Render as environment variables. Do not put real secrets into GitHub.

## 7. Smoke Test the Deployed API

```bash
python3 scripts/smoke_test_deploy.py --base-url https://YOUR-RENDER-API-URL
```
