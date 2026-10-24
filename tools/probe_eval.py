import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import torch, config as C
from transformers import AutoModelForCausalLM, AutoTokenizer
import eval as E

tok = AutoTokenizer.from_pretrained(str(C.BASE_DIR), trust_remote_code=True)
ids = E.option_token_ids(tok)
print("opt ids:", ids, [tok.decode([i]) for i in ids])
m = AutoModelForCausalLM.from_pretrained(str(C.BASE_DIR), dtype=torch.bfloat16, device_map={"": 0})
m.eval(); m.config.use_cache = False
rows = E.read_jsonl(C.PROC / "medqa.jsonl")[:6]
for r in rows:
    p = tok.apply_chat_template(E.build_messages(r), tokenize=False, add_generation_prompt=True)
    e = tok(p, return_tensors="pt", add_special_tokens=False).to("cuda")
    with torch.inference_mode():
        lg = m(**e).logits[0, -1].float()
    top = torch.topk(lg, 5)
    print(repr(r["answer"]), "| logits A-D:", [round(float(lg[i]), 2) for i in ids],
          "| top:", [(tok.decode([int(t)]), round(float(v), 2)) for v, t in zip(top.values, top.indices)])
print("tail of prompt:", repr(p[-80:]))
