import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError


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


def pack_stats(pack_dir: Path) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    for item in pack_dir.rglob("*"):
        if not item.is_file():
            continue
        file_count += 1
        total_bytes += item.stat().st_size
    return total_bytes, file_count


def upload_pack_large(
    api: HfApi,
    *,
    repo_id: str,
    source_dir: Path,
    pack_dir: Path,
    num_workers: int | None,
) -> None:
    parent_dir = source_dir.parent
    relative_pattern = f"{source_dir.name}/{pack_dir.name}/**"
    api.upload_large_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(parent_dir),
        allow_patterns=[relative_pattern],
        num_workers=num_workers,
        print_report=True,
        print_report_every=60,
    )


def repair_existing_pack(
    api: HfApi,
    *,
    repo_id: str,
    path_in_repo: str,
    pack_dir: Path,
) -> tuple[int, int]:
    uploaded = 0
    skipped = 0
    for local_file in sorted([item for item in pack_dir.rglob("*") if item.is_file()]):
        repo_path = f"{path_in_repo}/{pack_dir.name}/{str(local_file.relative_to(pack_dir)).replace(os.sep, '/')}"
        if api.file_exists(repo_id=repo_id, repo_type="dataset", filename=repo_path):
            skipped += 1
            continue
        api.upload_file(
            path_or_fileobj=str(local_file),
            path_in_repo=repo_path,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Repair pack {pack_dir.name} @ {datetime.now(timezone.utc).isoformat()}",
        )
        uploaded += 1
        print(f"Uploaded missing file {uploaded} for existing pack {pack_dir.name}: {repo_path}")
    return uploaded, skipped


def with_retries(label: str, fn, retries: int):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except HfHubHTTPError as exc:
            last_error = exc
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code not in (502, 503, 504) or attempt >= retries:
                raise
            wait_seconds = min(20, attempt * 5)
            print(f"{label} failed with HTTP {status_code}; retrying in {wait_seconds}s ({attempt}/{retries})")
            time.sleep(wait_seconds)
    if last_error is not None:
        raise last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload local static asset packs to a private HF dataset repo.")
    parser.add_argument("--repo-id", default="", help="Explicit dataset repo id, e.g. owner/champion-council-packs")
    parser.add_argument("--suffix", default=os.environ.get("PACKS_REPO_SUFFIX", "champion-council-packs"))
    parser.add_argument("--source-dir", default="static/assets/packs")
    parser.add_argument("--path-in-repo", default=os.environ.get("PACKS_DATASET_ROOT", "packs"))
    parser.add_argument("--private", action="store_true", default=True)
    parser.add_argument("--force", action="store_true", help="Re-upload packs even if manifest exists in the dataset repo.")
    parser.add_argument("--repair-existing", action="store_true", help="Upload any missing files inside packs that already exist remotely.")
    parser.add_argument("--pack", action="append", default=[], help="Restrict sync to one or more specific pack ids.")
    parser.add_argument("--large-threshold-bytes", type=int, default=250 * 1024 * 1024, help="Use upload_large_folder when a pack reaches this size.")
    parser.add_argument("--large-threshold-files", type=int, default=500, help="Use upload_large_folder when a pack reaches this file count.")
    parser.add_argument("--num-workers", type=int, default=4, help="Worker count for upload_large_folder.")
    parser.add_argument("--skip-index", action="store_true", help="Do not upload packs/index.json during this run.")
    parser.add_argument("--retries", type=int, default=3, help="Retry transient HF 5xx failures this many times.")
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

    index_path = source_dir / "index.json"
    index_repo_path = f"{path_in_repo}/index.json"
    if index_path.exists() and not args.skip_index:
        index_exists = with_retries(
            "Check remote pack index",
            lambda: api.file_exists(repo_id=repo_id, repo_type="dataset", filename=index_repo_path),
            int(args.retries),
        )
        if args.force or not index_exists:
            with_retries(
                "Upload pack index",
                lambda: api.upload_file(
                    path_or_fileobj=str(index_path),
                    path_in_repo=index_repo_path,
                    repo_id=repo_id,
                    repo_type="dataset",
                    commit_message=f"Sync pack index @ {datetime.now(timezone.utc).isoformat()}",
                ),
                int(args.retries),
            )
            print(f"Uploaded index -> dataset://{repo_id}/{path_in_repo}/index.json")
        else:
            print(f"Skipping existing index -> dataset://{repo_id}/{path_in_repo}/index.json")

    pack_filter = {str(item).strip() for item in (args.pack or []) if str(item).strip()}
    pack_dirs = sorted(
        [item for item in source_dir.iterdir() if item.is_dir() and (item / "manifest.json").exists()],
        key=lambda item: item.name.lower(),
    )
    if pack_filter:
        pack_dirs = [item for item in pack_dirs if item.name in pack_filter]
    uploaded = 0
    skipped = 0
    repaired_uploaded = 0
    repaired_skipped = 0
    for pack_dir in pack_dirs:
        manifest_repo_path = f"{path_in_repo}/{pack_dir.name}/manifest.json"
        manifest_exists = with_retries(
            f"Check remote manifest for {pack_dir.name}",
            lambda: api.file_exists(repo_id=repo_id, repo_type="dataset", filename=manifest_repo_path),
            int(args.retries),
        )
        if manifest_exists and not args.force:
            if args.repair_existing:
                current_uploaded, current_skipped = repair_existing_pack(
                    api,
                    repo_id=repo_id,
                    path_in_repo=path_in_repo,
                    pack_dir=pack_dir,
                )
                repaired_uploaded += current_uploaded
                repaired_skipped += current_skipped
                print(
                    f"Repaired existing pack {pack_dir.name}: "
                    f"uploaded_missing={current_uploaded} already_present={current_skipped}"
                )
                continue
            skipped += 1
            print(f"Skipping existing pack: {pack_dir.name}")
            continue
        total_bytes, file_count = pack_stats(pack_dir)
        use_large = total_bytes >= int(args.large_threshold_bytes) or file_count >= int(args.large_threshold_files)
        if use_large:
            print(
                f"Uploading large pack via resumable lane: {pack_dir.name} "
                f"(files={file_count} bytes={total_bytes})"
            )
            with_retries(
                f"Upload large pack {pack_dir.name}",
                lambda: upload_pack_large(
                    api,
                    repo_id=repo_id,
                    source_dir=source_dir,
                    pack_dir=pack_dir,
                    num_workers=int(args.num_workers) if args.num_workers else None,
                ),
                int(args.retries),
            )
        else:
            with_retries(
                f"Upload pack {pack_dir.name}",
                lambda: api.upload_folder(
                    folder_path=str(pack_dir),
                    path_in_repo=f"{path_in_repo}/{pack_dir.name}",
                    repo_id=repo_id,
                    repo_type="dataset",
                    commit_message=f"Sync pack {pack_dir.name} @ {datetime.now(timezone.utc).isoformat()}",
                ),
                int(args.retries),
            )
        uploaded += 1
        print(f"Uploaded pack {uploaded}/{len(pack_dirs)}: {pack_dir.name}")

    print(
        f"Pack dataset sync complete: uploaded={uploaded} skipped={skipped} "
        f"repaired_uploaded={repaired_uploaded} repaired_skipped={repaired_skipped} "
        f"source={source_dir} repo=dataset://{repo_id}/{path_in_repo}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
