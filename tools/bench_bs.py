"""Micro-benchmark: steps/second for the 3B LoRA+checkpointing setup on this GPU.

Usage: python -u tools/bench_bs.py [--base models/...] [--gc 0|1]
"""
import argparse
import time

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser()
p.add_argument("--base", default="models/Qwen2.5-3B-Instruct")
p.add_argument("--gc", type=int, default=1)
p.add_argument("--cases", default="1:512,2:512,4:384,2:640")
a = p.parse_args()

print("loading", a.base, flush=True)
try:
    model = AutoModelForCausalLM.from_pretrained(str(ROOT / a.base), dtype=torch.bfloat16,
                                                trust_remote_code=True).cuda()
except TypeError:
    model = AutoModelForCausalLM.from_pretrained(str(ROOT / a.base), torch_dtype=torch.bfloat16,
                                                trust_remote_code=True).cuda()
model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                                         task_type="CAUSAL_LM",
                                         target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                         "gate_proj", "up_proj", "down_proj"]))
model.config.use_cache = False
if a.gc:
    model.gradient_checkpointing_enable()
model.train()
opt = torch.optim.AdamW([q for q in model.parameters() if q.requires_grad], lr=1e-4)

for case in a.cases.split(","):
    bs, sl = (int(x) for x in case.split(":"))
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    ids = torch.randint(0, 1000, (bs, sl), device="cuda")
    lab = ids.clone()
    try:
        for _ in range(2):                                    # warmup
            out = model(input_ids=ids, labels=lab)
            out.loss.backward()
            opt.step()
            opt.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        t0 = time.time()
        n = 3
        for _ in range(n):
            out = model(input_ids=ids, labels=lab)
            out.loss.backward()
            opt.step()
            opt.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        dt = (time.time() - t0) / n
        peak = torch.cuda.max_memory_allocated() / 2**30
        print(f"  bs={bs} len={sl}: {dt:6.2f} s/step  {bs / dt:5.2f} samp/s  "
              f"{bs * sl / dt / 1000:5.1f} ktok/s  peak {peak:.2f} GiB", flush=True)
    except torch.cuda.OutOfMemoryError:
        print(f"  bs={bs} len={sl}: OOM", flush=True)
        torch.cuda.empty_cache()
