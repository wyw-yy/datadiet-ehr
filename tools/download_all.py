"""Download the model and the three datasets through the hf-mirror endpoint.

Run:  python tools/download_all.py            (models + all datasets)
      python tools/download_all.py --no-model (datasets only)

Everything lands under the project root:
  models/Qwen2.5-3B-Instruct/
  data/raw/healthcaremagic|medqa|medmcqa/
"""
import os
import sys
import time
import traceback

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
# hf-xet's chunk cache fails on this box with "os error 5 (access denied)";
# force the plain HTTP path instead of the Xet backend.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from huggingface_hub import snapshot_download  # noqa: E402  (needs the env above)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JOBS = [
    # (label, repo_id, repo_type, local_dir, ignore patterns)
    ("model  Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "model",
     os.path.join(ROOT, "models", "Qwen2.5-3B-Instruct"),
     ["*.gguf", "*.bin", "*.h5", "*.msgpack", "*.onnx", "original/*"]),
    ("data   HealthCareMagic-100k", "lavita/ChatDoctor-HealthCareMagic-100k", "dataset",
     os.path.join(ROOT, "data", "raw", "healthcaremagic"), ["*.png", "*.jpg"]),
    ("data   MedQA-USMLE-4-options", "GBaker/MedQA-USMLE-4-options", "dataset",
     os.path.join(ROOT, "data", "raw", "medqa"), ["*.png", "*.jpg", "*.pdf"]),
    ("data   MedMCQA", "openlifescienceai/medmcqa", "dataset",
     os.path.join(ROOT, "data", "raw", "medmcqa"), ["*.png", "*.jpg"]),
]


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def dir_size(path):
    total = 0
    for base, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def main():
    want_model = "--no-model" not in sys.argv
    print(f"endpoint = {os.environ['HF_ENDPOINT']}", flush=True)
    failures = []
    for label, repo, rtype, local, ignore in JOBS:
        if not want_model and rtype == "model":
            continue
        print(f"\n=== {label}  ({repo})", flush=True)
        t0 = time.time()
        try:
            path = snapshot_download(repo_id=repo, repo_type=rtype, local_dir=local,
                                     ignore_patterns=ignore, max_workers=4)
            size = dir_size(path)
            print(f"    ok  -> {path}  ({human(size)})  {time.time() - t0:.0f}s", flush=True)
        except Exception as exc:  # keep going, report at the end
            print(f"    FAILED: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            failures.append(label)
    print("\n--- summary ---", flush=True)
    for label, _r, _t, local, _i in JOBS:
        if not want_model and _t == "model":
            continue
        state = "MISSING" if not os.path.isdir(local) else human(dir_size(local))
        print(f"  {label:32s} {state}", flush=True)
    if failures:
        print(f"\n{len(failures)} target(s) failed: {failures}", flush=True)
        sys.exit(1)
    print("\nall downloads complete", flush=True)


if __name__ == "__main__":
    main()
