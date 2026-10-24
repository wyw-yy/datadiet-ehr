import urllib.request, time

u = "https://huggingface.co/datasets/lavita/ChatDoctor-HealthCareMagic-100k/resolve/main/data/train-00000-of-00001-5e7cb295b9cff0bf.parquet"
req = urllib.request.Request(u, headers={"Range": "bytes=0-8388607", "User-Agent": "Mozilla/5.0"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=60) as r:
    n = 0
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        n += len(b)
dt = time.time() - t0
print(f"got {n/1048576:.2f} MB in {dt:.1f}s = {n/1048576/dt:.2f} MB/s, status={r.status}")
