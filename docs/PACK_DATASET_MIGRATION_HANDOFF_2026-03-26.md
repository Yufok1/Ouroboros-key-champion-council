# Pack Dataset Migration Handoff

Date: 2026-03-26

## Goal

Move the heavy `static/assets/packs` payload out of the Hugging Face Space repo and into a private HF dataset repo, while keeping the runtime/browser contract unchanged:

- Browser still requests `/static/assets/packs/index.json`
- Browser still requests `/static/assets/packs/<pack_id>/...`
- Space server resolves those paths from:
  1. local repo files first
  2. dataset-backed cache second

This is the intended fix for the private Space push failure caused by the Space repo Git/LFS path refusing the giant pack payload.

## Current Local State

Runtime checkpoint already committed earlier:

- `6cd3806` `Refactor inhabitant into mounted character runtime surfaces`

Current uncommitted migration changes:

- [server.py](/F:/End-Game/champion_councl/server.py)
- [pack_storage.py](/F:/End-Game/champion_councl/pack_storage.py)
- [.gitignore](/F:/End-Game/champion_councl/.gitignore)
- [scripts/sync-pack-dataset.py](/F:/End-Game/champion_councl/scripts/sync-pack-dataset.py)

Syntax check already passed:

```powershell
python -m py_compile server.py persistence.py pack_storage.py scripts/sync-pack-dataset.py
```

## What Was Implemented

### 1. Runtime pack storage module

New file:

- [pack_storage.py](/F:/End-Game/champion_councl/pack_storage.py)

Key behavior:

- derives a private HF dataset repo id for packs
- uses the existing `HF_TOKEN` pattern already used by `persistence.py`
- resolves a writable pack cache dir:
  - `/data/champion-council-packs` on Spaces if available
  - `./data/champion-council-packs` locally
- syncs dataset contents into a local cache with `snapshot_download(...)`
- serves pack files from local repo first, cache second

Default dataset repo naming:

- `{owner}/champion-council-packs`

Default dataset layout:

- `packs/index.json`
- `packs/<pack_id>/manifest.json`
- `packs/<pack_id>/<asset files>`

### 2. Server routes and startup hook

Patched in [server.py](/F:/End-Game/champion_councl/server.py):

- startup logs pack storage status and calls `pack_storage.bootstrap_runtime_packs()`
- `GET /api/packs/status`
- `POST /api/packs/sync`
- `GET /static/assets/packs/{pack_path:path}`

Important:

- this pack route is defined before the generic `/static` mount, so it can intercept pack requests
- if local `static/assets/packs/...` files are later removed from the Space repo, the browser URLs still work through this route

### 3. Upload helper

New file:

- [scripts/sync-pack-dataset.py](/F:/End-Game/champion_councl/scripts/sync-pack-dataset.py)

Purpose:

- create/update the private HF dataset repo for packs
- upload `static/assets/packs/index.json`
- upload pack directories one-by-one under `packs/<pack_id>/...`
- resumable by rerun: it skips a pack if `packs/<pack_id>/manifest.json` already exists in the dataset repo

Also patched [.gitignore](/F:/End-Game/champion_councl/.gitignore) so this helper is not ignored.

## Size / Scope

Local pack tree measured:

- files: `7187`
- bytes: `4414644286`
- GiB: `4.111`
- manifest count: `60`

That pack payload is exactly why it should not stay in the Space repo push path.

## HF Repo State Observed

Private Space repo:

- `origin/main` remained at `f33eb40`
- repeated full pushes to the Space failed on the server side with:
  - `Repository storage limit reached (Max: 1 GB)`

Private dataset repo created for packs:

- `tostido/champion-council-packs`
- private dataset repo creation succeeded

Last confirmed dataset repo contents before the second aborted upload check:

- only `.gitattributes`

The first monolithic `upload_folder(...)` approach timed out after about an hour and did not materially populate the repo.

Then the upload helper was rewritten to use resumable pack-by-pack uploads.

## Important Caveat Before Resuming Upload

The user aborted the later pack upload because it was saturating bandwidth.

Before resuming upload, the next agent should check for lingering local uploader processes and stop them if they are still active.

Observed local processes at one point:

- several long-running `python.exe` processes existed, including one new process started during the pack upload attempt

Do not assume the upload is fully stopped without checking.

## Next-Agent Checklist

### A. Verify local state

1. Confirm current uncommitted files:
   - [server.py](/F:/End-Game/champion_councl/server.py)
   - [pack_storage.py](/F:/End-Game/champion_councl/pack_storage.py)
   - [.gitignore](/F:/End-Game/champion_councl/.gitignore)
   - [scripts/sync-pack-dataset.py](/F:/End-Game/champion_councl/scripts/sync-pack-dataset.py)
2. Run:

```powershell
python -m py_compile server.py persistence.py pack_storage.py scripts/sync-pack-dataset.py
```

### B. Check for lingering uploader/background processes

Use something like:

```powershell
Get-Process python,git,git-lfs -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,StartTime,CPU |
  Sort-Object StartTime
```

If a stale uploader is still running and consuming bandwidth, stop only that process, not unrelated runtime processes.

### C. Check dataset repo progress before uploading again

Expected dataset repo id:

- `tostido/champion-council-packs`

Inspect current file count before resuming:

```powershell
$env:HF_TOKEN='...'
@'
import os, json
from huggingface_hub import HfApi
api = HfApi(token=os.environ["HF_TOKEN"])
files = api.list_repo_files(repo_id="tostido/champion-council-packs", repo_type="dataset")
print(json.dumps({"count": len(files), "sample": files[:20]}, indent=2))
'@ | python -
```

### D. Resume pack dataset upload

Use the resumable uploader:

```powershell
$env:HF_TOKEN='...'
python scripts/sync-pack-dataset.py --repo-id tostido/champion-council-packs
```

Notes:

- the script uploads `index.json` first
- then uploads each pack directory under `packs/<pack_id>`
- rerunning it is expected and safe; already-present packs are skipped unless `--force` is added
- if bandwidth is sensitive, run it when the user is okay with a long upload

### E. Verify runtime pull path locally

After some packs exist in the dataset repo, test:

1. `GET /api/packs/status`
2. `POST /api/packs/sync`
3. `GET /static/assets/packs/index.json`
4. `GET /static/assets/packs/<pack_id>/manifest.json`

Expected behavior:

- local repo packs still work immediately
- if local files are missing later, dataset cache should satisfy the same URLs

### F. Only after dataset upload is ready: slim the Space repo

Planned end-state:

- remove heavy content under `static/assets/packs/*` from the Space repo
- rely on [server.py](/F:/End-Game/champion_councl/server.py) + [pack_storage.py](/F:/End-Game/champion_councl/pack_storage.py) to serve packs from the dataset-backed cache

Do not slim the repo until the dataset repo is populated enough to boot and browse packs.

### G. Push the Space repo after slimming

Once the heavy pack tree is out of the Space repo, retry the Space push. The expectation is that this avoids the previous Space repo LFS/storage failure path.

## Recommended Env / Config

For the Space runtime:

- `HF_TOKEN` with access to the private dataset repo
- optional `PACKS_REPO_ID=tostido/champion-council-packs`
- optional `PACKS_SYNC_ON_START=1`
- optional `PACKS_DATA_DIR=/data/champion-council-packs`

If `/data` persistent storage is available, use it for pack cache so cold starts do not re-download everything.

## What To Avoid

- Do not keep retrying full `main` pushes with the heavy pack tree still inside the Space repo.
- Do not assume account-level private storage quota fixes the Space repo push path.
- Do not expose tokens in logs, docs, or commits.

## Intent For The Next Agent

Finish the pack dataset migration and Space slim-down. The correct continuation is:

1. resume dataset upload
2. verify dataset-backed pack serving
3. remove heavy local pack tree from the Space repo
4. push the slim Space repo

Do not reopen the earlier argument about whether the Space itself runs the server. It does. The point of this migration is to let the Space stay runnable while moving only the heavy pack payload out of the Space repo push path.
