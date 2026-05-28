# ============================================================
#  COPY-PASTE THIS INTO A GOOGLE COLAB NOTEBOOK
#  Each section marked with # --- CELL --- goes into a new cell
# ============================================================

# --- CELL 1: Install ComfyUI & Dependencies ---
# Run this cell FIRST. It installs everything on the Colab GPU machine.

!apt-get -qq install -y aria2 > /dev/null 2>&1
!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
!pip install -q aiohttp einops transformers safetensors accelerate pyyaml pillow scipy

import os
os.chdir("/content")

# Clone ComfyUI
if not os.path.exists("/content/ComfyUI"):
    !git clone https://github.com/comfyanonymous/ComfyUI.git
    os.chdir("/content/ComfyUI")
    !pip install -q -r requirements.txt
else:
    os.chdir("/content/ComfyUI")

print("✅ ComfyUI installed!")


# --- CELL 2: Download AI Models ---
# This downloads AnythingXL (images) and Wan2.1 (video) to the Colab GPU machine.
# Colab has FAST internet (~1 Gbps) so this takes only a few minutes.

import os
os.chdir("/content/ComfyUI")

MODELS = {
    # AnythingXL for manhwa-style images
    "models/checkpoints/AnythingXL_xl.safetensors": 
        "https://huggingface.co/Lykon/AnyLoRA/resolve/main/AnythingXL_xl.safetensors",
    
    # Wan2.1 1.3B for video generation
    "models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors":
        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors",
    
    # Wan2.1 CLIP text encoder
    "models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors":
        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    
    # Wan2.1 VAE
    "models/vae/wan_2.1_vae.safetensors":
        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
}

for local_path, url in MODELS.items():
    full_path = os.path.join("/content/ComfyUI", local_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path):
        print(f"⬇️  Downloading {os.path.basename(local_path)}...")
        !aria2c -x 16 -s 16 -k 1M --dir="{os.path.dirname(full_path)}" --out="{os.path.basename(full_path)}" "{url}"
    else:
        print(f"✅ Already have {os.path.basename(local_path)}")

# Install SaveWEBM custom node (for video output)
CUSTOM_NODES_DIR = "/content/ComfyUI/custom_nodes"
if not os.path.exists(f"{CUSTOM_NODES_DIR}/ComfyUI-VideoHelperSuite"):
    os.chdir(CUSTOM_NODES_DIR)
    !git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    os.chdir("/content/ComfyUI")

print("\n✅ All models downloaded!")


# --- CELL 3: Start ComfyUI Server ---
# This starts ComfyUI in the background and creates a public tunnel URL.

import subprocess, threading, time, re

# Start ComfyUI as a background process
comfy_proc = subprocess.Popen(
    ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--dont-print-server"],
    cwd="/content/ComfyUI",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT
)

# Wait for ComfyUI to fully start
print("⏳ Waiting for ComfyUI to start...")
time.sleep(15)
print("✅ ComfyUI server started on port 8188!")


# --- CELL 4: Create Public Tunnel ---
# This exposes your Colab ComfyUI to the internet so your local PC can reach it.

import subprocess, time

# Install cloudflared
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared
!chmod +x /usr/local/bin/cloudflared

# Start the tunnel in the background
tunnel_proc = subprocess.Popen(
    ["cloudflared", "tunnel", "--url", "http://localhost:8188", "--no-autoupdate"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Wait and extract the public URL
time.sleep(8)
output = tunnel_proc.stderr.read(4096).decode()

import re
urls = re.findall(r'https://[a-z0-9\-]+\.trycloudflare\.com', output)

if urls:
    COLAB_URL = urls[0]
    print("=" * 60)
    print(f"🌐 YOUR COLAB COMFYUI URL:")
    print(f"   {COLAB_URL}")
    print("=" * 60)
    print()
    print("📋 Copy this URL and paste it into your .env file on your PC:")
    print(f'   COMFYUI_URL={COLAB_URL}')
    print()
    print("Then run on your PC:")
    print("   python orchestrator.py generate --limit 3 --remote")
else:
    print("❌ Could not extract tunnel URL. Check the output below:")
    print(output)


# --- CELL 5: Keep Alive (Run this and leave Colab open) ---
# This keeps the Colab session alive while your PC sends jobs.

import time

print("🟢 Colab ComfyUI is running! Leave this tab open.")
print("   Your local orchestrator.py can now send jobs here.")
print("   Press the ⏹ Stop button when you're done for the day.")

try:
    while True:
        time.sleep(60)
        print(".", end="", flush=True)
except KeyboardInterrupt:
    print("\n🔴 Session ended.")
