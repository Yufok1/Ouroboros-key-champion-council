import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi


def env_token() -> str:
    return (
        os.environ.get("HF_TOKEN", "")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN", "")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN", "")
    ).strip()


def derive_repo_id(explicit: str | None, suffix: str) -> str:
    if explicit:
        return explicit.strip()
    owner = (
        os.environ.get("PACKS_REPO_OWNER", "").strip()
        or os.environ.get("SPACE_AUTHOR_NAME", "").strip()
    )
    if not owner:
        space_id = os.environ.get("SPACE_ID", "").strip()
        if "/" in space_id:
            owner = space_id.split("/", 1)[0].strip()
    if not owner:
        raise SystemExit("Missing repo owner. Set PACKS_REPO_OWNER / SPACE_AUTHOR_NAME or pass --repo-id.")
    return f"{owner}/{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload local static asset packs to a private HF dataset repo.")
    parser.add_argument("--repo-id", default="", help="Explicit dataset repo id, e.g. owner/champion-council-packs")
    parser.add_argument("--suffix", default=os.environ.get("PACKS_REPO_SUFFIX", "champion-council-packs"))
    parser.add_argument("--source-dir", default="static/assets/packs")
    parser.add_argument("--path-in-repo", default=os.environ.get("PACKS_DATASET_ROOT", "packs"))
    parser.add_argument("--private", action="store_true", default=True)
    parser.add_argument("--force", action="store_true", help="Re-upload packs even if manifest exists in the dataset repo.")
    args = parser.parse_args()

    token = env_token()
    if not token:
        raise SystemExit("Missing HF token in HF_TOKEN / HUGGING_FACE_HUB_TOKEN / HUGGINGFACEHUB_API_TOKEN.")

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source dir does not exist: {source_dir}")

    repo_id = derive_repo_id(args.repo_id or None, str(args.suffix or "champion-council-packs"))
    path_in_repo = str(args.path_in_repo or "packs").strip().strip("/") or "packs"

    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=bool(args.private), exist_ok=True)

    existing = set(api.list_repo_files(repo_id=repo_id, repo_type="dataset"))

    index_path = source_dir / "index.json"
    if index_path.exists():
        api.upload_file(
            path_or_fileobj=str(index_path),
            path_in_repo=f"{path_in_repo}/index.json",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Sync pack index @ {datetime.now(timezone.utc).isoformat()}",
        )
        print(f"Uploaded index -> dataset://{repo_id}/{path_in_repo}/index.json")

    pack_dirs = sorted(
        [item for item in source_dir.iterdir() if item.is_dir() and (item / "manifest.json").exists()],
        key=lambda item: item.name.lower(),
    )
    uploaded = 0
    skipped = 0
    for pack_dir in pack_dirs:
        manifest_repo_path = f"{path_in_repo}/{pack_dir.name}/manifest.json"
        if not args.force and manifest_repo_path in existing:
            skipped += 1
            print(f"Skipping existing pack: {pack_dir.name}")
            continue
        api.upload_folder(
            folder_path=str(pack_dir),
            path_in_repo=f"{path_in_repo}/{pack_dir.name}",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Sync pack {pack_dir.name} @ {datetime.now(timezone.utc).isoformat()}",
        )
        uploaded += 1
        print(f"Uploaded pack {uploaded}/{len(pack_dirs)}: {pack_dir.name}")

    print(
        f"Pack dataset sync complete: uploaded={uploaded} skipped={skipped} "
        f"source={source_dir} repo=dataset://{repo_id}/{path_in_repo}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
