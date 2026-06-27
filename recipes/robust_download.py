#!/usr/bin/env python3
"""Robust HF downloader with stall-watchdog (macOS has no `timeout`).
Monitors cache growth; if no growth for STALL_SECS, kill the `hf download`
subprocess and retry (resumes from cache). Loops until it exits cleanly.
Usage: robust_download.py <repo> [filename]
"""
import subprocess, time, os, sys

HF = os.path.expanduser("~/.local/share/uv/tools/mflux/bin/hf")
repo = sys.argv[1]
filename = sys.argv[2] if len(sys.argv) > 2 else None
CACHE = os.path.expanduser(
    "~/.cache/huggingface/hub/models--" + repo.replace("/", "--"))
STALL_SECS = 45
POLL = 10
MAX_ATTEMPTS = 150

env = dict(os.environ, HF_HUB_ENABLE_HF_TRANSFER="0", HF_HUB_DOWNLOAD_TIMEOUT="30")
cmd = [HF, "download", repo] + ([filename] if filename else [])


def cache_bytes():
    t = 0
    for root, _, files in os.walk(CACHE):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return t


print(f"== robust_download {repo} {filename or ''}", flush=True)
for attempt in range(1, MAX_ATTEMPTS + 1):
    p = subprocess.Popen(cmd, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last, last_t, stalled = cache_bytes(), time.time(), False
    while p.poll() is None:
        time.sleep(POLL)
        cur = cache_bytes()
        if cur > last:
            last, last_t = cur, time.time()
        elif time.time() - last_t > STALL_SECS:
            p.kill()
            stalled = True
            break
    rc = p.wait()
    print(f"[{attempt}] {time.strftime('%H:%M:%S')} rc={rc} "
          f"stalled={stalled} cache={cache_bytes()/1e9:.1f}GB", flush=True)
    if rc == 0 and not stalled:
        print("OK_COMPLETE", flush=True)
        sys.exit(0)
    time.sleep(2)
print("GAVE_UP", flush=True)
sys.exit(1)
