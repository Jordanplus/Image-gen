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
    parser = argparse.ArgumentParser(description="Mac M-Series 本地 AI 算圖 CLI 介面")
    parser.add_argument("-p", "--prompt", type=str, required=True, help="正向提示詞 (Prompt)")
    parser.add_argument("-np", "--negative_prompt", type=str, default="anime, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, poor quality, bad anatomy", help="負向提示詞")
    parser.add_argument("-r", "--ref", nargs="+", help="臉部參考圖片路徑 (可提供多張，用空格隔開，例如: -r face1.jpg face2.jpg)")
    parser.add_argument("-s", "--seed", type=int, help="固定 Seed，用以微調或重現風格")
    parser.add_argument("-iw", "--ip_weight", type=float, default=0.85, help="臉部鎖定權重 (預設 0.85)")
    # 預設使用 Juggernaut XL (最頂級寫實模型)
    parser.add_argument("-m", "--model", type=str, default="juggernautXL_v9Rdphoto2Lightning.safetensors", help="模型檔案名稱 (必須位在 ComfyUI/models/checkpoints/ 中)")
    
    args = parser.parse_args()
    
    seed = args.seed if args.seed is not None else random.randint(1, 999999999999999)
    
    # 判斷是否使用 Identity Lock (IP-Adapter)
    if args.ref and len(args.ref) > 1:
        workflow_path = "workflows/legacy/workflow_api_multi_face.json"
    elif args.ref and len(args.ref) == 1:
        workflow_path = "workflows/legacy/workflow_api_with_ipadapter.json"
    else:
        workflow_path = "workflows/legacy/workflow_api.json"
    
    if not os.path.exists(workflow_path):
        print(f"❌ 錯誤: 找不到 {workflow_path}。請確保它在目前目錄下。")
        sys.exit(1)
        
    with open(workflow_path, "r") as f:
        workflow = json.load(f)
        
    # 動態綁定參數至 ComfyUI 節點 (對應我們預設的 JSON 架構)
    for node_id, node_data in workflow.items():
        class_type = node_data.get("class_type")
        if class_type == "KSampler":
            node_data["inputs"]["seed"] = seed
        elif class_type == "CheckpointLoaderSimple":
            node_data["inputs"]["ckpt_name"] = args.model
        elif class_type == "IPAdapterAdvanced":
            node_data["inputs"]["weight"] = args.ip_weight
    
    # 處理 Prompt 節點綁定 (根據我們自訂的 JSON 模板: 6 是正向, 7 是負向)
    if "6" in workflow and workflow["6"]["class_type"] == "CLIPTextEncode":
        workflow["6"]["inputs"]["text"] = args.prompt
    if "7" in workflow and workflow["7"]["class_type"] == "CLIPTextEncode":
        workflow["7"]["inputs"]["text"] = args.negative_prompt

    # 處理參考圖片 (Identity Lock)
    if args.ref:
        print(f"🔒 啟動特徵鎖定...")
        # For single image
        if len(args.ref) == 1:
            target_img_path = args.ref[0]
            if not os.path.exists(target_img_path):
                print(f"❌ 錯誤: 參考圖片路徑不存在: {target_img_path}")
                sys.exit(1)
            
            for node_id, node_data in workflow.items():
                if node_data["class_type"] == "LoadImage":
                    img_name = "face_" + os.path.basename(target_img_path)
                    dest = os.path.join("ComfyUI", "input", img_name)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy(target_img_path, dest)
                    node_data["inputs"]["image"] = img_name
        
        # For multi-image blending
        elif len(args.ref) > 1:
            ipa_node_id = None
            for n_id, n_data in workflow.items():
                if n_data["class_type"] == "IPAdapterAdvanced":
                    ipa_node_id = n_id
                    break

            load_nodes = []
            for i, img_path in enumerate(args.ref):
                if not os.path.exists(img_path):
                    print(f"❌ 錯誤: 參考圖片路徑不存在: {img_path}")
                    sys.exit(1)
                    
                img_name = f"multi_face_{i}_" + os.path.basename(img_path)
                dest = os.path.join("ComfyUI", "input", img_name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy(img_path, dest)
                
                node_id = f"load_{i}"
                workflow[node_id] = {
                    "inputs": {"image": img_name, "upload": "image"},
                    "class_type": "LoadImage"
                }
                load_nodes.append(node_id)
            
            # Build batch chain
            last_out = load_nodes[0]
            for i in range(1, len(load_nodes)):
                batch_node_id = f"batch_{i}"
                workflow[batch_node_id] = {
                    "inputs": {
                        "image1": [last_out, 0],
                        "image2": [load_nodes[i], 0]
                    },
                    "class_type": "ImageBatch"
                }
                last_out = batch_node_id
            
            # Connect final batch to IPAdapter
            if ipa_node_id:
                workflow[ipa_node_id]["inputs"]["image"] = [last_out, 0]
            
            # Clean up old nodes 11 and 20 to avoid unused node errors
            if "11" in workflow: del workflow["11"]
            if "20" in workflow: del workflow["20"]
            
        print(f"✅ 臉部特徵鎖定準備就緒 (共 {len(args.ref)} 張圖片)")

    print(f"🚀 提交任務至本地 Mac 後台...")
    print(f"   ➤ 模型: {args.model}")
    print(f"   ➤ 指令: {args.prompt}")
    print(f"   ➤ Seed: {seed}")

    response = queue_prompt(workflow)
    prompt_id = response['prompt_id']
    
    print(f"⏳ 任務已排隊 (ID: {prompt_id})。這可能需要幾十秒到幾分鐘 (依據模型大小而定)...")
    
    # Polling for completion
    while True:
        history = check_history(prompt_id)
        if prompt_id in history:
            break
        time.sleep(2)
        
    history_data = history[prompt_id]
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    # 下載並儲存生成的圖片
    for node_id in history_data['outputs']:
        node_output = history_data['outputs'][node_id]
        if 'images' in node_output:
            for image in node_output['images']:
                image_data = get_image(image['filename'], image['subfolder'], image['type'])
                
                timestamp = int(time.time())
                out_path = os.path.join(OUTPUT_DIR, f"result_{timestamp}_{seed}.png")
                with open(out_path, "wb") as f:
                    f.write(image_data)
                print(f"✅ 產圖完成！圖片已儲存至: {out_path}")

if __name__ == "__main__":
    main()
