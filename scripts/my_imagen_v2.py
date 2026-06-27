import argparse
import json
import urllib.request
import urllib.parse
import os
import time
import random
import sys
import shutil

COMFY_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "./outputs"

def queue_prompt(prompt_workflow):
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request(f"{COMFY_URL}/prompt", data=data)
    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    except urllib.error.URLError as e:
        print(f"❌ 無法連線至 ComfyUI 後台: {e}")
        print("💡 請確保您已經在另一個終端機執行了: ./start_backend.sh")
        sys.exit(1)

def check_history(prompt_id):
    req = urllib.request.Request(f"{COMFY_URL}/history/{prompt_id}")
    response = urllib.request.urlopen(req)
    return json.loads(response.read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    req = urllib.request.Request(f"{COMFY_URL}/view?{url_values}")
    response = urllib.request.urlopen(req)
    return response.read()

def main():
    parser = argparse.ArgumentParser(description="Mac M-Series 本地 AI 算圖 CLI V2 (核彈級臉部修復版)")
    parser.add_argument("-p", "--prompt", type=str, required=True, help="正向提示詞 (Prompt)")
    parser.add_argument("-np", "--negative_prompt", type=str, default="anime, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, poor quality, bad anatomy", help="負向提示詞")
    parser.add_argument("-r", "--ref", nargs="+", help="臉部參考圖片路徑 (可提供多張)")
    parser.add_argument("-s", "--seed", type=int, help="固定 Seed")
    parser.add_argument("-iw", "--ip_weight", type=float, default=0.85, help="臉部鎖定權重 (預設 0.85)")
    parser.add_argument("-m", "--model", type=str, default="juggernautXL_v9Rdphoto2Lightning.safetensors", help="模型名稱")
    
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.randint(1, 999999999999999)
    t_start = time.time()
    
    workflow_path = "workflows/workflow_api_face_fix.json"
    if not os.path.exists(workflow_path):
        print(f"❌ 錯誤: 找不到 {workflow_path}")
        sys.exit(1)
        
    with open(workflow_path, "r") as f:
        workflow = json.load(f)
        
    # 動態參數綁定
    for node_id, node_data in workflow.items():
        class_type = node_data.get("class_type")
        if class_type == "KSampler":
            node_data["inputs"]["seed"] = seed
        elif class_type == "FaceDetailer":
            node_data["inputs"]["seed"] = seed
        elif class_type == "CheckpointLoaderSimple":
            node_data["inputs"]["ckpt_name"] = args.model
        elif class_type == "IPAdapterAdvanced":
            node_data["inputs"]["weight"] = args.ip_weight
            
    if "6" in workflow: workflow["6"]["inputs"]["text"] = args.prompt
    if "7" in workflow: workflow["7"]["inputs"]["text"] = args.negative_prompt

    # 處理多圖參考 (與 V1 邏輯相同，但針對 V2 JSON 優化)
    if args.ref:
        print(f"🔒 啟動核彈級特徵鎖定...")
        load_nodes = []
        for i, img_path in enumerate(args.ref):
            if not os.path.exists(img_path):
                print(f"❌ 錯誤: 路徑不存在: {img_path}"); sys.exit(1)
            img_name = f"v2_face_{i}_" + os.path.basename(img_path)
            dest = os.path.join("ComfyUI", "input", img_name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(img_path, dest)
            
            node_id = f"load_{i}"
            workflow[node_id] = {"inputs": {"image": img_name, "upload": "image"}, "class_type": "LoadImage"}
            load_nodes.append(node_id)
        
        last_out = load_nodes[0]
        for i in range(1, len(load_nodes)):
            batch_node_id = f"batch_{i}"
            workflow[batch_node_id] = {"inputs": {"image1": [last_out, 0], "image2": [load_nodes[i], 0]}, "class_type": "ImageBatch"}
            last_out = batch_node_id
        
        # 將最終 Batch 連接至所有 IPAdapterAdvanced 節點 (10 是基礎, 40 是修復)
        if "10" in workflow: workflow["10"]["inputs"]["image"] = [last_out, 0]
        if "40" in workflow: workflow["40"]["inputs"]["image"] = [last_out, 0]
        if "25" in workflow: del workflow["25"]
        if "900" in workflow: del workflow["900"]

    print(f"🚀 提交【臉部修復版】任務至 Mac 後台...")
    response = queue_prompt(workflow)
    prompt_id = response['prompt_id']
    print(f"⏳ 正在進行二次重繪與修復 (ID: {prompt_id})...")
    
    while True:
        history = check_history(prompt_id)
        if prompt_id in history: break
        time.sleep(2)
        
    history_data = history[prompt_id]
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
        
    for node_id in history_data['outputs']:
        node_output = history_data['outputs'][node_id]
        if 'images' in node_output:
            for image in node_output['images']:
                image_data = get_image(image['filename'], image['subfolder'], image['type'])
                out_path = os.path.join(OUTPUT_DIR, f"facefix_{int(time.time())}_{seed}.png")
                with open(out_path, "wb") as f: f.write(image_data)
                print(f"✅ 完美神似版產圖完成！路徑: {out_path}")

    elapsed = time.time() - t_start
    time_log = os.path.join(OUTPUT_DIR, "gen_times.log")
    with open(time_log, "a") as lf:
        lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {elapsed:7.1f}s | seed={seed} | ip_weight={args.ip_weight} | refs={len(args.ref) if args.ref else 0}\n")
    print(f"⏱️  本次跑圖耗時: {elapsed:.1f} 秒（已記錄到 {time_log}）")

if __name__ == "__main__":
    main()
