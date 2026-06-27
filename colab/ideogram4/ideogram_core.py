"""
Colab-side text-to-image core for Ideogram 4.0 (NF4) on a T4 GPU.

NOT run directly. `run_ideogram.sh` prepends three data globals then ships the
combined script to a Colab T4 via `colab run`:

    PROMPT   = "<text prompt>"
    CFG      = {"W":1024,"H":1024,"STEPS":28,"SEED":1405,"CFG_SCALE":None,"REPO":"..."}
    HF_TOKEN = "<hf token with the ideogram-4 license accepted>"

It loads Ideogram4Pipeline (NF4) with CPU offload (a 16GB T4 can't hold the
whole 9.3B pipe), generates one image, and prints it as base64 between
<<<PNG_B64_START>>> / <<<PNG_B64_END>>>.

Design mirrors cloude-colab-video-gen/scripts/i2v_core.py.
"""
import os, sys, time, base64, traceback, subprocess

# Ideogram4Pipeline only exists in bleeding-edge diffusers; Colab's preinstalled
# transformers 5.x breaks diffusers' encoder path -> cap below 5. Wheels cache on
# the VM only within a session, so a one-shot `colab run` pays this each time.
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "git+https://github.com/huggingface/diffusers.git",
                "transformers<5", "accelerate", "bitsandbytes",
                "sentencepiece", "protobuf", "huggingface_hub"], check=False)

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
if HF_TOKEN:
    os.environ.setdefault("HF_TOKEN", HF_TOKEN)
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", HF_TOKEN)

import torch, transformers, diffusers
print(f"diffusers={diffusers.__version__} transformers={transformers.__version__} "
      f"torch={torch.__version__} cuda={torch.cuda.is_available()}", flush=True)
if torch.cuda.is_available():
    cc = torch.cuda.get_device_capability(0)
    free, total = torch.cuda.mem_get_info()
    print(f"gpu={torch.cuda.get_device_name(0)} cc={cc} "
          f"vram_total={total/1e9:.1f}GB free={free/1e9:.1f}GB", flush=True)

W = CFG["W"]; H = CFG["H"]; STEPS = CFG.get("STEPS", 28); SEED = CFG.get("SEED", 1405)
CFG_SCALE = CFG.get("CFG_SCALE")
REPO = CFG.get("REPO", "ideogram-ai/ideogram-4-nf4-diffusers")

try:
    from diffusers import Ideogram4Pipeline
    from transformers import AutoTokenizer
except Exception as e:
    print("RESULT_FAIL Ideogram4Pipeline missing in installed diffusers ->",
          repr(e)[:200], flush=True)
    sys.exit(1)

# --- Confirmed-required fixes for the ideogram-4-nf4-diffusers checkpoint (2026-06-27) ---
# fix #1: the text encoder is a full Qwen3-VL; its rotary embedding crashes when
# config.rope_scaling is None (missing None-guard in transformers 4.57.x).
import transformers.models.qwen3_vl.modeling_qwen3_vl as _q3
_orig_rope = _q3.Qwen3VLTextRotaryEmbedding.__init__
def _rope_init(self, config, *a, **k):
    if getattr(config, "rope_scaling", None) is None:
        try:
            config.rope_scaling = {}
        except Exception:
            pass
    return _orig_rope(self, config, *a, **k)
_q3.Qwen3VLTextRotaryEmbedding.__init__ = _rope_init

t = time.time()
try:
    # fix #2: checkpoint ships only tokenizer.json (fast format), but declares the
    # slow Qwen2Tokenizer -> vocab_file=None crash. Force the fast tokenizer in.
    tok = AutoTokenizer.from_pretrained(REPO, subfolder="tokenizer",
                                        use_fast=True, token=os.environ.get("HF_TOKEN"))
    # T4 is Turing (compute 7.5) — no bf16 tensor cores, so use fp16 compute,
    # NOT the bfloat16 the official model card shows for 24GB Ampere/Ada cards.
    # ⚠️ Model is ~16GB (Qwen3-VL 5.5G + 2x transformer 5.2G). enable_model_cpu_offload
    # (below) pins it all in host RAM -> a FREE Colab T4 (~13GB RAM) OOMs and the
    # runtime dies here. Needs an L4/24GB-class GPU (more VRAM AND more host RAM).
    pipe = Ideogram4Pipeline.from_pretrained(
        REPO, tokenizer=tok, torch_dtype=torch.float16, token=os.environ.get("HF_TOKEN"))
except Exception as e:
    print("RESULT_FAIL load failed ->", repr(e)[:300], flush=True)
    traceback.print_exc()
    sys.exit(1)

# 16GB T4: never .to('cuda') the whole pipe; stream components on demand.
try:
    pipe.enable_model_cpu_offload()
except Exception as e:
    print("model_cpu_offload n/a ->", repr(e)[:120], flush=True)
for fn in ("enable_vae_slicing", "enable_vae_tiling", "enable_attention_slicing"):
    try:
        getattr(pipe, fn)()
    except Exception:
        pass
print(f"pipeline ready {time.time()-t:.0f}s (cpu offload, fp16)", flush=True)

# Pipeline call signature is not yet pinned in public docs — probe it so unknown
# kwargs don't hard-fail the run.
import inspect
sig = inspect.signature(pipe.__call__)
kw = dict(height=H, width=W, generator=torch.manual_seed(SEED))
if "num_inference_steps" in sig.parameters:
    kw["num_inference_steps"] = STEPS
if CFG_SCALE is not None and "guidance_scale" in sig.parameters:
    kw["guidance_scale"] = CFG_SCALE

t = time.time()
try:
    img = pipe(PROMPT, **kw).images[0]
except torch.cuda.OutOfMemoryError as e:
    print(f"RESULT_FAIL OutOfMemory at {W}x{H} ->", repr(e)[:160],
          "| retry with smaller -W/-H", flush=True)
    sys.exit(1)
except Exception as e:
    print("RESULT_FAIL generate failed ->", repr(e)[:300], flush=True)
    traceback.print_exc()
    sys.exit(1)
print(f"generated {W}x{H} steps={kw.get('num_inference_steps','?')} "
      f"{time.time()-t:.0f}s", flush=True)

out = "/content/ideogram_out.png"
img.save(out)
data = open(out, "rb").read()
print("RESULT_OK FILE_BYTES", len(data), flush=True)
print("<<<PNG_B64_START>>>", flush=True)
print(base64.b64encode(data).decode(), flush=True)
print("<<<PNG_B64_END>>>", flush=True)
