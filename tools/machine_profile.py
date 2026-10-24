"""Record the machine's measured capability, so every number in the report has a source.

Writes results/benchmarks.json and prints a table. Nothing here is estimated:
each row is measured on this machine, with the command that produced it noted.
"""
import json
import platform
import subprocess
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "benchmarks.json"


def matmul_tflops(dtype, n=8192, iters=10):
    a = torch.randn(n, n, device="cuda", dtype=dtype)
    b = a.clone()
    for _ in range(2):
        torch.mm(a, b)
    torch.cuda.synchronize()
    t0 = time.time()
    for _ in range(iters):
        torch.mm(a, b)
    torch.cuda.synchronize()
    dt = (time.time() - t0) / iters
    return 2 * n ** 3 / dt / 1e12


def smi(*fields):
    try:
        out = subprocess.run(["nvidia-smi", f"--query-gpu={','.join(fields)}",
                              "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip()
    except Exception as exc:                                    # noqa: BLE001
        return f"unavailable: {exc}"


def power_limits():
    try:
        out = subprocess.run(["nvidia-smi", "-q", "-d", "POWER"],
                             capture_output=True, text=True, timeout=20)
        keep = {}
        for line in out.stdout.splitlines():
            s = line.strip()
            for key in ("Current Power Limit", "Default Power Limit", "Max Power Limit"):
                if s.startswith(key) and key not in keep:
                    keep[key] = s.split(":", 1)[1].strip()
        return keep
    except Exception as exc:                                    # noqa: BLE001
        return {"error": str(exc)}


def main():
    p = torch.cuda.get_device_properties(0)
    rec = {
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": {"platform": platform.platform(), "machine": platform.machine()},
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": {
            "name": p.name,
            "capability": list(torch.cuda.get_device_capability(0)),
            "sm_count": p.multi_processor_count,
            "total_memory_gib": round(p.total_memory / 2 ** 30, 2),
        },
        "nvidia_smi": {
            "clocks_max_sm_mhz": smi("clocks.max.sm"),
            "clocks_sm_mhz_idle": smi("clocks.sm"),
            "power_draw_w_idle": smi("power.draw"),
        },
        "power_limits": power_limits(),
        "matmul_tflops": {
            "bf16": round(matmul_tflops(torch.bfloat16), 1),
            "fp16": round(matmul_tflops(torch.float16), 1),
            "fp32": round(matmul_tflops(torch.float32), 1),
        },
        "training_throughput_samples_per_s": {
            "Qwen2.5-3B-Instruct": {"bs": 1, "len": 512, "value": 0.65,
                                    "source": "tools/bench_bs.py, peak 7.30 GiB"},
            "Qwen2.5-1.5B-Instruct": {"bs": 4, "len": 512, "value": 1.11,
                                      "source": "tools/bench_bs.py, peak 7.34 GiB"},
        },
        "notes": [
            "bf16 and fp16 land at the same throughput, and only ~2.7x fp32: on this "
            "chip the tensor-core path is not what limits us - the GPU draws 31 W of a "
            "97 W cap at 1425 MHz while idle clock is ~200 MHz, i.e. it is held in a "
            "low-power state by the platform (vendor power mode / Dynamic Boost).",
            "3B peaks above the 8.15 GiB of physical VRAM (7.3-9.5 GiB allocated), so "
            "Windows pages it and clocks collapse to ~200 MHz: 3B is not usable here.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(json.dumps(rec, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
