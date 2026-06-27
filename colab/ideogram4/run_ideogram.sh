#!/usr/bin/env bash
# colab-ideogram — generate one Ideogram 4.0 (NF4) image on a Colab T4 and retrieve the PNG locally.
#
# Usage:
#   HF_TOKEN=hf_xxx run_ideogram.sh -o OUT.png [-g L4] [-W 1024] [-H 1024] \
#                   [--steps 28] [--seed 1405] [--cfg 3.5] "PROMPT"
#
# Requires: `colab` CLI (ADC auth), python3, base64. HF_TOKEN must be a HuggingFace
# token whose account has accepted the ideogram-4 gated license.
# NOTE: default GPU is L4 (24GB). A free T4 (16GB VRAM / ~13GB host RAM) OOMs while
# loading this ~16GB model — see README "實測結論". Mirrors run_video.sh.

set -uo pipefail

OUT=""; GPU="L4"; W=1024; H=1024; STEPS=28; SEED=1405; CFGS="None"
COLAB="${COLAB:-$HOME/.local/bin/colab}"; [ -x "$COLAB" ] || COLAB=colab
HERE="$(cd "$(dirname "$0")" && pwd)"
CORE="$HERE/ideogram_core.py"

usage() { sed -n '2,9p' "$0"; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -o) OUT="$2"; shift 2;;
    -g|--gpu) GPU="$2"; shift 2;;
    -W) W="$2"; shift 2;;
    -H) H="$2"; shift 2;;
    --steps) STEPS="$2"; shift 2;;
    --seed) SEED="$2"; shift 2;;
    --cfg) CFGS="$2"; shift 2;;
    -h|--help) usage 0;;
    --) shift; break;;
    -*) echo "unknown flag: $1" >&2; usage 2;;
    *) break;;
  esac
done

[ -n "$OUT" ] || { echo "ERROR: -o OUT.png is required" >&2; usage 2; }
[ -f "$CORE" ] || { echo "ERROR: core not found: $CORE" >&2; exit 2; }
[ $# -ge 1 ] || { echo "ERROR: need a PROMPT" >&2; usage 2; }
: "${HF_TOKEN:?set HF_TOKEN env (HF token with the ideogram-4 license accepted)}"
PROMPT="$1"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
SC="$TMP/selfcontained.py"

# --- assemble: prepend data globals, then the core ---
{
  python3 -c 'import json,sys; print("PROMPT = "+json.dumps(sys.argv[1]))' "$PROMPT"
  echo "CFG = {\"W\": $W, \"H\": $H, \"STEPS\": $STEPS, \"SEED\": $SEED, \"CFG_SCALE\": $CFGS}"
  python3 -c 'import json,sys; print("HF_TOKEN = "+json.dumps(sys.argv[1]))' "$HF_TOKEN"
  cat "$CORE"
} > "$SC"
echo "[skill] assembled $(wc -c < "$SC" | tr -d ' ') bytes @ ${W}x${H} steps=$STEPS seed=$SEED"

echo "[skill] colab run --gpu $GPU (one-shot, auto-stop; first run pip-installs + downloads ~16GB) ..."
"$COLAB" --auth=adc run --gpu "$GPU" "$SC" > "$TMP/out.txt" 2> "$TMP/err.txt"
echo "[skill] run exit=$?"
# status/progress only — never echo the PNG_B64 payload (the token never matches these patterns)
grep -aE "RESULT_OK|RESULT_FAIL|pipeline ready|generated|gpu=|diffusers=|OutOfMemory|Error|terminated|lost" \
  "$TMP/out.txt" "$TMP/err.txt" 2>/dev/null | grep -av PNG_B64 | tail -20

awk '/<<<PNG_B64_START>>>/{f=1;next} /<<<PNG_B64_END>>>/{f=0} f' "$TMP/out.txt" \
  | python3 -c "import sys,base64; sys.stdout.buffer.write(base64.b64decode(''.join(sys.stdin.read().split())))" \
  > "$OUT" 2>/dev/null

if [ -s "$OUT" ]; then
  echo "[skill] OK -> $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
  command -v sips >/dev/null 2>&1 && \
    sips -g pixelWidth -g pixelHeight "$OUT" 2>/dev/null | grep -E "pixel(Width|Height)"
else
  echo "[skill] FAILED — no PNG decoded. Last stderr:" >&2
  grep -av PNG_B64 "$TMP/err.txt" 2>/dev/null | tail -15 >&2
  exit 1
fi
