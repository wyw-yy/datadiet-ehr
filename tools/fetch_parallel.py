"""Multi-connection range downloader.

The China mirrors throttle each TCP connection to ~0.4-0.7 MB/s, but they
scale with concurrency (6 connections measured 2.35 MB/s aggregate). This
script splits every file into chunks and pulls them in parallel, then
reassembles the file. Resumable: existing chunks are skipped.

Usage:
    python tools/fetch_parallel.py <manifest.json> [--workers 12]

manifest.json:
    [{"url": "...", "dest": "models/x/model-00001-of-00002.safetensors"}, ...]
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CHUNK = 8 * 1024 * 1024          # 8 MB per range request
PARTS_DIR = ".parts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
LOCK = threading.Lock()


def head(url):
    """Probe size with a 1-byte range GET (ModelScope's HEAD returns no
    Content-Length, so HEAD is useless here)."""
    req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cr = r.headers.get("Content-Range") or ""
        total = 0
        if "/" in cr:
            try:
                total = int(cr.rsplit("/", 1)[1])
            except ValueError:
                total = 0
        if total == 0:
            total = int(r.headers.get("Content-Length") or 0)
        ranges = bool(cr) or "bytes" in (r.headers.get("Accept-Ranges") or "").lower()
        final = r.geturl()
    return total, ranges, final


def fetch_range(url, start, end, dest, tries=8):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) != end - start + 1:
                raise IOError(f"short read {len(data)} != {end - start + 1}")
            with open(dest, "wb") as f:
                f.write(data)
            return len(data)
        except Exception as exc:
            last = exc
            if attempt == tries - 1:
                break
            # 429 = mirror rate limit; 5xx = transient. Back off gently, then hard.
            code = getattr(exc, "code", None)
            wait = 2.0 * (attempt + 1) if code not in (429, 503) else min(60.0, 5.0 * 2 ** attempt)
            time.sleep(wait)
    raise last


def download(url, dest, workers, known_size=0):
    dest = os.path.abspath(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if known_size:
        size, ranged, final = int(known_size), True, url
    else:
        size, ranged, final = head(url)
    if size == 0:
        raise IOError(f"no content-length for {url}")
    label = os.path.basename(dest)
    if os.path.exists(dest) and os.path.getsize(dest) == size:
        print(f"  [{label}] already complete ({size / 1e6:.1f} MB)", flush=True)
        return size
    if not ranged:
        print(f"  [{label}] server does not support ranges, single stream", flush=True)
        urllib.request.urlretrieve(final, dest)
        return size

    parts = os.path.join(os.path.dirname(dest), PARTS_DIR, label)
    os.makedirs(parts, exist_ok=True)
    jobs = []
    for i, start in enumerate(range(0, size, CHUNK)):
        end = min(start + CHUNK, size) - 1
        part = os.path.join(parts, f"{i:05d}")
        if os.path.exists(part) and os.path.getsize(part) == end - start + 1:
            continue
        jobs.append((i, start, end, part))

    total = len(jobs)
    if total:
        print(f"  [{label}] {size / 1e6:.1f} MB, {total} chunks to fetch "
              f"({workers} workers)", flush=True)
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_range, final, s, e, p): (i, s, e, p) for i, s, e, p in jobs}
        for fut in as_completed(futs):
            fut.result()
            with LOCK:
                done += 1
                if done % 10 == 0 or done == total:
                    el = time.time() - t0
                    got = done * CHUNK / 1e6
                    print(f"    {done}/{total} chunks, {got:.0f} MB, "
                          f"{got / max(el, 1e-9):.2f} MB/s", flush=True)

    tmp = dest + ".assembling"
    with open(tmp, "wb") as out:
        for i, start in enumerate(range(0, size, CHUNK)):
            end = min(start + CHUNK, size) - 1
            part = os.path.join(parts, f"{i:05d}")
            with open(part, "rb") as f:
                out.write(f.read())
    got = os.path.getsize(tmp)
    if got != size:
        raise IOError(f"assembled {got} != {size} for {dest}")
    os.replace(tmp, dest)
    import shutil
    shutil.rmtree(parts, ignore_errors=True)
    print(f"  [{label}] ok {size / 1e6:.1f} MB in {time.time() - t0:.0f}s", flush=True)
    return size


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/fetch_parallel.py manifest.json [--workers N]")
    manifest_path = sys.argv[1]
    workers = 12
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"{len(manifest)} file(s), {workers} workers each", flush=True)
    failures = []
    for item in manifest:
        name = os.path.basename(item["dest"])
        print(f"\n=== {name}", flush=True)
        try:
            download(item["url"], item["dest"], workers, int(item.get("size") or 0))
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
            failures.append(name)
    print("\n--- summary ---", flush=True)
    for item in manifest:
        d = os.path.abspath(item["dest"])
        state = f"{os.path.getsize(d) / 1e6:.1f} MB" if os.path.exists(d) else "MISSING"
        print(f"  {os.path.basename(d):45s} {state}", flush=True)
    if failures:
        print(f"\n{len(failures)} failed: {failures}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
