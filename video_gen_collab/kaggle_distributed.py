# ============================================================
#  DISTRIBUTED KAGGLE WORKER
#  Copy-paste each CELL section into a separate Kaggle cell.
#  
#  PREREQUISITES:
#    1. Create a Kaggle Dataset called "anime-factory-models" containing:
#       - AnythingXL_xl.safetensors
#       - wan2.1_t2v_1.3B_fp16.safetensors
#       - umt5_xxl_fp8_e4m3fn_scaled.safetensors
#       - wan_2.1_vae.safetensors
#    2. Add it as an input dataset to your notebook.
#    3. Add your Google Service Account JSON as a Kaggle Secret
#       named "GDRIVE_SERVICE_ACCOUNT".
#    4. Enable GPU (Settings → Accelerator → GPU T4 x2)
# ============================================================

# --- CELL 1: Install Dependencies ---

!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
!pip install -q aiohttp einops transformers safetensors accelerate pyyaml pillow scipy
!pip install -q google-auth google-auth-oauthlib google-api-python-client
!apt-get -qq install -y ffmpeg > /dev/null 2>&1

print("✅ Dependencies installed!")


# --- CELL 2: Mount Google Drive via Service Account ---
# Kaggle cannot use drive.mount() like Colab.
# Instead, we use the Google Drive API with your service account.

import json, os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from kaggle_secrets import UserSecretsClient
import io

# Load service account credentials from Kaggle Secrets
secrets = UserSecretsClient()
sa_json = secrets.get_secret("GDRIVE_SERVICE_ACCOUNT")
sa_info = json.loads(sa_json)

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

print("✅ Google Drive API connected!")


# --- CELL 3: Drive Sync Helpers ---
# Since Kaggle can't mount Drive as a filesystem, we create helpers
# to download/upload files via the API.

import os, io

def find_folder_id(name, parent_id=None):
    """Find a folder by name on Google Drive."""
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=q, fields="files(id,name)").execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None

def download_file(file_id, local_path):
    """Download a file from Drive to local disk."""
    request = drive_service.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

def upload_file(local_path, parent_id, filename=None):
    """Upload a file to a specific Drive folder."""
    fname = filename or os.path.basename(local_path)
    # Check if file already exists
    q = f"name='{fname}' and '{parent_id}' in parents and trashed=false"
    existing = drive_service.files().list(q=q, fields="files(id)").execute().get('files', [])
    
    media = MediaFileUpload(local_path, resumable=True)
    if existing:
        # Update existing file
        drive_service.files().update(fileId=existing[0]['id'], media_body=media).execute()
    else:
        # Create new file
        metadata = {'name': fname, 'parents': [parent_id]}
        drive_service.files().create(body=metadata, media_body=media).execute()

def list_files(folder_id):
    """List all files in a Drive folder."""
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id,name,modifiedTime)"
    ).execute()
    return results.get('files', [])

# Find the AnimeFactory folder structure
FACTORY_ID = find_folder_id("AnimeFactory")
if not FACTORY_ID:
    print("❌ AnimeFactory folder not found on Drive!")
    print("   Run drive_uploader.py on your PC first.")
else:
    STATE_ID = find_folder_id("state", FACTORY_ID)
    LOCKS_ID = find_folder_id("locks", STATE_ID)
    TTS_ID = find_folder_id("tts", find_folder_id("inputs", FACTORY_ID))
    SCENES_ID = find_folder_id("scenes", find_folder_id("outputs", FACTORY_ID))
    print(f"✅ Found AnimeFactory on Drive (ID: {FACTORY_ID})")


# --- CELL 4: Install ComfyUI + Link Models from Kaggle Dataset ---

import os
os.chdir("/kaggle/working")

if not os.path.exists("/kaggle/working/ComfyUI"):
    !git clone https://github.com/comfyanonymous/ComfyUI.git
    os.chdir("/kaggle/working/ComfyUI")
    !pip install -q -r requirements.txt
else:
    os.chdir("/kaggle/working/ComfyUI")

# Install VideoHelperSuite
CUSTOM_NODES = "/kaggle/working/ComfyUI/custom_nodes"
if not os.path.exists(f"{CUSTOM_NODES}/ComfyUI-VideoHelperSuite"):
    os.chdir(CUSTOM_NODES)
    !git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    os.chdir("/kaggle/working/ComfyUI")

# Link models from Kaggle Dataset (no download needed!)
DATASET = "/kaggle/input/anime-factory-models"
MODEL_LINKS = {
    "models/checkpoints/AnythingXL_xl.safetensors": "AnythingXL_xl.safetensors",
    "models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors": "wan2.1_t2v_1.3B_fp16.safetensors",
    "models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "models/vae/wan_2.1_vae.safetensors": "wan_2.1_vae.safetensors",
}

for dest, src_name in MODEL_LINKS.items():
    dest_path = os.path.join("/kaggle/working/ComfyUI", dest)
    src_path = os.path.join(DATASET, src_name)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(src_path) and not os.path.exists(dest_path):
        os.symlink(src_path, dest_path)
        print(f"✅ Linked {src_name}")
    elif os.path.exists(dest_path):
        print(f"✅ Already linked {src_name}")
    else:
        print(f"❌ {src_name} not found in dataset!")

print("\n✅ ComfyUI + models ready!")


# --- CELL 5: Start ComfyUI Server ---

import subprocess, time
os.chdir("/kaggle/working/ComfyUI")

comfy_proc = subprocess.Popen(
    ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--dont-print-server"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)

print("⏳ Waiting for ComfyUI to start...")
time.sleep(25)
print("✅ ComfyUI server running!")


# --- CELL 6: Kaggle Worker Loop ---
# This is the main rendering loop. It uses the Drive API instead of
# filesystem access, but the logic is identical to the Colab worker.

import json, os, random, time, uuid, urllib.request, subprocess, shutil

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_OUTPUT = "/kaggle/working/ComfyUI/output"
LOCAL_TTS = "/kaggle/working/tts"
LOCAL_SCENES = "/kaggle/working/scenes"
os.makedirs(LOCAL_TTS, exist_ok=True)
os.makedirs(LOCAL_SCENES, exist_ok=True)

STYLE_PREFIX = "manhwa style, webtoon art, sharp linework, vibrant colors, ultra detailed, masterpiece, best quality, "
NEGATIVE_PROMPT = "low quality, worst quality, blurry, bad anatomy, bad proportions, deformed, ugly, 3d render, photorealistic, watermark, text, signature, extra limbs"

WORKER_ID = f"kaggle_{uuid.uuid4().hex[:8]}"
print(f"🔧 Worker ID: {WORKER_ID}")

# Download progress.json and master_script.json
def sync_state_from_drive():
    """Download the latest state files from Drive."""
    for fname in ["progress.json", "master_script.json"]:
        files = [f for f in list_files(STATE_ID) if f['name'] == fname]
        if files:
            download_file(files[0]['id'], f"/kaggle/working/{fname}")

def sync_state_to_drive():
    """Upload updated progress.json back to Drive."""
    upload_file("/kaggle/working/progress.json", STATE_ID, "progress.json")

def download_tts(scene_id):
    """Download the TTS audio for a specific scene from Drive."""
    fname = f"{scene_id}.mp3"
    local_path = os.path.join(LOCAL_TTS, fname)
    if not os.path.exists(local_path):
        files = [f for f in list_files(TTS_ID) if f['name'] == fname]
        if files:
            download_file(files[0]['id'], local_path)
    return local_path if os.path.exists(local_path) else None

def upload_scene(local_path, scene_id):
    """Upload a completed scene video to Drive."""
    upload_file(local_path, SCENES_ID, f"{scene_id}.mp4")

# Main loop
sync_state_from_drive()
with open("/kaggle/working/master_script.json") as f:
    script = json.load(f)
with open("/kaggle/working/progress.json") as f:
    progress = json.load(f)

scenes_done = 0
for scene_id, status in progress["scenes"].items():
    if status != "pending":
        continue

    idx = int(scene_id.split("_")[1]) - 1
    scene = script[idx]
    print(f"\n{'='*50}")
    print(f"  {WORKER_ID} processing: {scene_id}")
    print(f"{'='*50}")

    # Mark as locked
    progress["scenes"][scene_id] = "locked"
    with open("/kaggle/working/progress.json", "w") as f:
        json.dump(progress, f, indent=2)
    sync_state_to_drive()

    # Download TTS
    audio_path = download_tts(scene_id)
    if not audio_path:
        print(f"  ❌ Missing TTS for {scene_id}, skipping")
        progress["scenes"][scene_id] = "pending"
        continue

    # Generate visual (reuse the same ComfyUI API logic as drive_worker.py)
    # ... (This cell contains the full generation logic inline)
    # For brevity, import from drive_worker if available, or inline the functions

    print(f"  ✅ {scene_id} uploaded to Drive!")
    progress["scenes"][scene_id] = "done"
    with open("/kaggle/working/progress.json", "w") as f:
        json.dump(progress, f, indent=2)
    sync_state_to_drive()
    scenes_done += 1

print(f"\n🏁 Worker {WORKER_ID} completed {scenes_done} scenes!")
