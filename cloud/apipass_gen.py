#!/usr/bin/env python3
"""apipass.dev (task-based) gpt-image-2 / nano-banana adapter.

apipass.dev 是雲端影像的非同步轉售包裝：createTask → 輪詢 recordInfo → 取回 CDN 圖 URL，
與官方同步 schema 不同，故獨立成此 adapter。`generate_apipass()` 可被 generate_image.py
的 apipass 後端 import 重用（本機 ComfyUI 之外的「線上路線」）。

只依賴標準庫 + Pillow（urllib 走 HTTP，無需 SDK）。金鑰讀 APIPASS_API_KEY（或舊名 APIPASS_KEY），
預設集中於 /Users/mcgradymac/claude_prjs/apipass.env（被 generate_image.py 自動載入）。

CLI：
  export APIPASS_API_KEY=<apk_...>
  python apipass_gen.py --prompt-file p.txt -o out.png [--aspect 1:1] [--resolution 4K] [-r ref.png]
"""
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

# 金鑰自動載入：先讀 cwd 的 .env，再讀集中式 apipass.env（與 generate_image.py 一致，
# 讓本 adapter 單獨執行時也能用「apipass 環境」，無需手動 export APIPASS_API_KEY）。
APIPASS_ENV = "/Users/mcgradymac/claude_prjs/apipass.env"
try:
    from dotenv import load_dotenv
    load_dotenv()
    if os.path.exists(APIPASS_ENV):
        load_dotenv(APIPASS_ENV)
except ImportError:
    pass

API_BASE = "https://api.apipass.dev"
CREATE_PATH = "/api/v1/jobs/createTask"
RECORD_PATH = "/api/v1/jobs/recordInfo"
DEFAULT_MODEL = "openai/gpt-image-2"

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
DONE_BAD = {"fail", "failed", "error", "cancelled", "canceled", "timeout"}


def _key():
    k = os.environ.get("APIPASS_API_KEY") or os.environ.get("APIPASS_KEY") or ""
    if len(k) < 20:
        raise RuntimeError("APIPASS_API_KEY 未設定或過短（export APIPASS_API_KEY=<apk_...>）")
    return k


def _req(path, body=None, method="GET"):
    url = API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {_key()}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


# recordInfo 會「原樣回吐輸入」於這些 key（含我們送進去的參考圖 base64）→ 找結果時必須跳過，
# 否則會把輸入參考圖誤當成輸出（造成「回傳同一張圖」）。
_ECHO_KEYS = {"param", "params", "input", "request", "parameters", "payload"}


def _walk(obj, skip=()):
    """走訪 JSON 樹所有 (key, value)；遇到看似內嵌 JSON 的字串會展開再走（如 resultJson）。
    skip 內的 key 之子樹整個略過（用於排除回吐的輸入參數）。"""
    stack = [(None, obj)]
    while stack:
        k, v = stack.pop()
        if isinstance(k, str) and k.lower() in skip:
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                stack.append((kk, vv))
        elif isinstance(v, list):
            for item in v:
                stack.append((k, item))
        elif isinstance(v, str):
            yield k, v
            s = v.strip()
            if s[:1] in "{[" and len(s) > 2:
                try:
                    stack.append((k, json.loads(s)))
                except Exception:
                    pass


def _find_task_id(resp):
    for k, v in _walk(resp):
        if k and k.lower() in ("taskid", "task_id", "id", "jobid", "job_id") and isinstance(v, str) and v:
            return v
    return None


def _find_state(resp):
    for k, v in _walk(resp):
        if k and k.lower() in ("state", "status", "taskstatus", "successflag", "flag") and isinstance(v, (str, int)):
            return str(v).lower()
    return None


def _find_image(resp):
    """回傳 ('url', str) 或 ('b64', bytes) 或 None。跳過回吐輸入（_ECHO_KEYS）避免抓到輸入參考圖。"""
    for k, v in _walk(resp, skip=_ECHO_KEYS):
        if isinstance(v, str):
            low = v.lower()
            if low.startswith("http") and (any(e in low for e in IMG_EXT) or "cdn.apipass" in low or "results/task" in low):
                return ("url", v)
            if low.startswith("data:image"):
                return ("b64", base64.b64decode(v.split(",", 1)[1]))
            if len(v) > 5000 and k and "base64" in k.lower():
                try:
                    return ("b64", base64.b64decode(v))
                except Exception:
                    pass
    return None


def _download_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _save_image(data, output_filename):
    """依 output 副檔名正規化格式存檔（apipass 常回 JPEG；避免副檔名與內容不符）。"""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    ext = os.path.splitext(output_filename)[1].lower()
    if ext in (".jpg", ".jpeg"):
        img.convert("RGB").save(output_filename, "JPEG", quality=95)
    elif ext == ".webp":
        img.save(output_filename, "WEBP", quality=95)
    else:  # .png 等 → 依副檔名推斷
        img.save(output_filename)
    return os.path.getsize(output_filename)


def _image_ref(p):
    """本地檔 → data URI base64；已是 http(s) URL 則原樣傳。供 input.images（Identity Lock）。"""
    if isinstance(p, str) and p.lower().startswith("http"):
        return p
    ap = os.path.abspath(os.path.expanduser(p))
    ext = (os.path.splitext(ap)[1].lower().lstrip(".") or "png")
    mime = {"jpg": "jpeg"}.get(ext, ext)
    with open(ap, "rb") as f:
        b = base64.b64encode(f.read()).decode()
    return f"data:image/{mime};base64,{b}"


def generate_apipass(prompt, output_filename, aspect_ratio="1:1", resolution=None,
                     quality=None, images=None, model=DEFAULT_MODEL, base64_output=False,
                     poll=6, max_wait=300, log=print):
    """apipass 文生圖 / 圖生圖。成功回傳 output_filename，失敗回傳 None。

    resolution: None/"1K"/"2K"/"4K" → apipass input.resolution（小寫 1k/2k/4k）。
    quality:    None/"low"/"medium"/"high" → apipass input.quality（非 gpt-image 模型可能忽略）。
    images:     參考圖清單（本地路徑或 URL，最多 5）→ input.images，Identity Lock / image-to-image。
    """
    try:
        _key()
    except RuntimeError as e:
        log(f"錯誤：{e}")
        return None

    inp = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio or "1:1",
        "enable_base64_output": bool(base64_output),
    }
    if resolution:
        inp["resolution"] = resolution.lower()
    if quality:
        inp["quality"] = quality
    if images:
        refs = []
        for p in images[:5]:
            try:
                refs.append(_image_ref(p))
            except Exception as e:
                log(f"⚠️ 參考圖載入失敗 {p}: {e}")
        if not refs:
            log("❌ 要求參考圖但 0 張載入成功 — 中止。")
            return None
        inp["images"] = refs
        log(f"🖼️ Identity Lock：{len(refs)} 張參考圖 (input.images)")
    body = {"model": model, "input": inp}
    log(f"🚀 apipass createTask → {model} / aspect={aspect_ratio or '1:1'} / "
        f"res={resolution or '預設'} / quality={quality or '預設'} / refs={len(inp.get('images', []))}")
    try:
        create = _req(CREATE_PATH, body=body, method="POST")
    except Exception as e:
        log(f"💥 createTask 失敗：{e}")
        return None
    task_id = _find_task_id(create)
    if not task_id:
        log(f"❌ 找不到 taskId；createTask 回應：{json.dumps(create, ensure_ascii=False)[:400]}")
        return None
    log(f"🆔 taskId = {task_id}")

    waited = 0
    while waited < max_wait:
        time.sleep(poll)
        waited += poll
        try:
            info = _req(f"{RECORD_PATH}?taskId={task_id}", method="GET")
        except urllib.error.HTTPError:
            try:
                info = _req(RECORD_PATH, body={"taskId": task_id}, method="POST")
            except Exception as e:
                log(f"💥 recordInfo 失敗：{e}")
                return None
        img = _find_image(info)
        if img:
            kind, val = img
            try:
                data = _download_bytes(val) if kind == "url" else val
                if kind == "url":
                    log(f"🔗 結果 URL: {val}")
                n = _save_image(data, output_filename)
            except Exception as e:
                log(f"💥 下載/儲存失敗：{e}")
                return None
            log(f"✅ 已儲存 {n} bytes → {output_filename}")
            return output_filename
        state = _find_state(info)
        if state and any(b in state for b in DONE_BAD):
            log(f"❌ 任務失敗 state={state}；回應：{json.dumps(info, ensure_ascii=False)[:500]}")
            return None
        log(f"⏳ {waited}s… state={state}")
    log("❌ 逾時未取得結果。")
    return None


def main():
    ap = argparse.ArgumentParser(description="apipass.dev gpt-image-2 / nano-banana adapter")
    ap.add_argument("-p", "--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--aspect", default="1:1")
    ap.add_argument("-q", "--resolution", choices=["1K", "2K", "4K"], default=None,
                    help="apipass input.resolution（1k/2k/4k）")
    ap.add_argument("--quality", choices=["low", "medium", "high"], default=None,
                    help="apipass input.quality（gpt-image 用；nano-banana 可能忽略）")
    ap.add_argument("-r", "--ref", nargs="+", default=None,
                    help="參考圖（本地路徑或 URL，最多 5）→ Identity Lock / image-to-image")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base64", action="store_true")
    ap.add_argument("--poll", type=int, default=6)
    ap.add_argument("--max-wait", type=int, default=300)
    args = ap.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as f:
            prompt = f.read().strip()
    if not prompt:
        sys.exit("❌ 需要 -p 或 --prompt-file")

    ok = generate_apipass(prompt, args.output, aspect_ratio=args.aspect, resolution=args.resolution,
                          quality=args.quality, images=args.ref, model=args.model,
                          base64_output=args.base64, poll=args.poll, max_wait=args.max_wait)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
