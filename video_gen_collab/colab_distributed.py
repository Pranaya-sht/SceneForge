# ============================================================
#  DISTRIBUTED COLAB WORKER
#  Copy-paste each CELL section into a separate Colab cell
# ============================================================

# --- CELL 1: Mount Google Drive & Install Dependencies ---
# This gives the worker access to the shared state on Drive.

from google.colab import drive
drive.mount('/content/drive')

!apt-get -qq install -y aria2 ffmpeg > /dev/null 2>&1
!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
!pip install -q aiohttp einops transformers safetensors accelerate pyyaml pillow scipy

# Set the project path
DRIVE_ROOT = "/content/drive/MyDrive/AnimeFactory"
print(f"✅ Drive mounted. Factory root: {DRIVE_ROOT}")


# --- CELL 2: Install ComfyUI ---

import os
os.chdir("/content")

if not os.path.exists("/content/ComfyUI"):
    !git clone https://github.com/comfyanonymous/ComfyUI.git
    os.chdir("/content/ComfyUI")
    !pip install -q -r requirements.txt
else:
    os.chdir("/content/ComfyUI")

# Install VideoHelperSuite for SaveWEBM node
CUSTOM_NODES = "/content/ComfyUI/custom_nodes"
if not os.path.exists(f"{CUSTOM_NODES}/ComfyUI-VideoHelperSuite"):
    os.chdir(CUSTOM_NODES)
    !git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    os.chdir("/content/ComfyUI")

print("✅ ComfyUI installed!")


# --- CELL 3: Download AI Models ---
# Downloads AnythingXL (images) and Wan2.1 (video) to Colab's local disk.
# Colab's fast internet makes this take only ~3-5 minutes.

import os
os.chdir("/content/ComfyUI")

MODELS = {
    "models/checkpoints/AnythingXL_xl.safetensors":
        "https://huggingface.co/Lykon/AnyLoRA/resolve/main/AnythingXL_xl.safetensors",
    "models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors":
        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors",
    "models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors":
        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
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

print("\n✅ All models ready!")


# --- CELL 4: Start ComfyUI Server ---

import subprocess, time

os.chdir("/content/ComfyUI")
comfy_proc = subprocess.Popen(
    ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--dont-print-server"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)

print("⏳ Waiting for ComfyUI to start...")
time.sleep(20)
print("✅ ComfyUI server running on port 8188!")


# --- CELL 5: Copy Worker Scripts to Colab ---
# The worker scripts live on your Google Drive. We copy them locally for speed.

import shutil
REELS_DIR = "/content/drive/MyDrive/AnimeFactory/scripts"

# Copy worker scripts from Drive (you upload these once)
for script in ["drive_state.py", "drive_worker.py"]:
    src = os.path.join(REELS_DIR, script)
    dst = os.path.join("/content", script)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"✅ Copied {script}")
    else:
        print(f"⚠️  {script} not found on Drive at {src}")
        print(f"   Upload it to: {REELS_DIR}/{script}")

print("\n📋 If scripts are missing, upload them to:")
print(f"   {REELS_DIR}/drive_state.py")
print(f"   {REELS_DIR}/drive_worker.py")


# --- CELL 6: START THE WORKER ---
# This is the main cell. It runs the worker in a loop until all scenes are done.
# You can safely restart this cell if Colab disconnects.

DRIVE_ROOT = "/content/drive/MyDrive/AnimeFactory"
COMFYUI_OUTPUT = "/content/ComfyUI/output"

!python /content/drive_worker.py \
    --drive-path "{DRIVE_ROOT}" \
    --comfyui-output "{COMFYUI_OUTPUT}"


# --- CELL 7 (OPTIONAL): Check Progress ---
# Run this anytime to see how far along the pipeline is.

import sys
sys.path.insert(0, "/content")
from drive_state import DriveState

state = DriveState("/content/drive/MyDrive/AnimeFactory")
state.get_summary()


# --- CELL 8 (OPTIONAL): Final Stitch ---
# Run this AFTER all scenes are complete to create the final video.

import os, subprocess

DRIVE_ROOT = "/content/drive/MyDrive/AnimeFactory"
scenes_dir = os.path.join(DRIVE_ROOT, "outputs", "scenes")
final_path = os.path.join(DRIVE_ROOT, "outputs", "final_video.mp4")

# Get all completed scene files in order
scene_files = sorted([
    os.path.join(scenes_dir, f)
    for f in os.listdir(scenes_dir)
    if f.endswith(".mp4")
])

print(f"Found {len(scene_files)} completed scenes")

# Create concat list
list_file = os.path.join(DRIVE_ROOT, "outputs", "concat_list.txt")
with open(list_file, "w") as f:
    for sf in scene_files:
        f.write(f"file '{sf}'\n")

# Stitch
!ffmpeg -y -f concat -safe 0 -i "{list_file}" -c copy "{final_path}"
print(f"\n🎬 FINAL VIDEO: {final_path}")
print(f"   Size: {os.path.getsize(final_path) / 1024 / 1024:.1f} MB")
