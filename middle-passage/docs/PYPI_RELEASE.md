# PyPI Release Checklist

Package name: `middle-passage`

Current release posture:

- Phase 0 scaffold
- Synthetic-safe defaults
- No real sensitive coordinates in tests or examples
- Protection-first public language

## GitHub First

1. Push the source to GitHub.
2. Confirm CI passes for the `middle-passage` package.
3. Configure PyPI Trusted Publishing for:
   - PyPI project: `middle-passage`
   - GitHub repository: `Yufok1/Ouroboros-key-champion-council`
   - Workflow: `.github/workflows/middle-passage-publish.yml`
   - Environment: `pypi`
4. Create a GitHub release or run the publish workflow manually with the
   confirmation input.

## Local Dry Run

From `middle-passage/`:

```bash
python -m pip install --upgrade pip build twine pytest
python -m pytest -q
python -m build
python -m twine check dist/*
```

## Manual Upload Fallback

Only use a local upload if Trusted Publishing is unavailable:

```bash
python -m twine upload dist/*
```

Do not commit PyPI tokens, `.pypirc`, build artifacts, or credentials.
