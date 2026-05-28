"""
Generate self-contained Colab notebook for the distributed worker.
Run: python generate_notebooks.py
"""
import json, os

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def to_lines(text):
    """Convert a file's text into JSON notebook source lines."""
    lines = text.splitlines(keepends=True)
    # Last line shouldn't have a trailing newline in the JSON source array
    if lines and lines[-1].endswith("\n"):
        lines[-1] = lines[-1].rstrip("\n")
    return lines

def make_code(source_lines):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source_lines
    }

def make_markdown(text):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [text]
    }

# Read source files
drive_state_text = read_file("drive_state.py")
drive_worker_text = read_file("drive_worker.py")

drive_state_lines = to_lines(drive_state_text)
drive_worker_lines = to_lines(drive_worker_text)

cells = []

# ── HEADER ──────────────────────────────────────────────────────────────
cells.append(make_markdown(
    "# 🎬 Anime Factory — Distributed Cloud Worker\n"
    "Run cells **in order (1→9)**. GPU must be enabled: Runtime → Change runtime type → T4 GPU."
))

# ── CELL 1: Mount Drive + Install deps ──────────────────────────────────
cells.append(make_markdown("## Cell 1 — Mount Google Drive & Install Dependencies"))
cells.append(make_code([
    "# CELL 1: Mount Drive & install dependencies\n",
    "from google.colab import drive\n",
    "drive.mount('/content/drive', force_remount=True)\n",
    "\n",
    "import subprocess, sys\n",
    "print('Installing system tools...')\n",
    "subprocess.run(['apt-get', '-qq', 'install', '-y', 'aria2', 'ffmpeg'], check=True, capture_output=True)\n",
    "print('Installing Python packages...')\n",
    "subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'requests'], check=True, capture_output=True)\n",
    "print('✅ Cell 1 complete!')\n",
]))

# ── CELL 2: Download & Install ComfyUI ──────────────────────────────────
cells.append(make_markdown("## Cell 2 — Download & Install ComfyUI"))
cells.append(make_code([
    "# CELL 2: Install ComfyUI (skip if already done)\n",
    "import os\n",
    "if not os.path.exists('/content/ComfyUI'):\n",
    "    print('Cloning ComfyUI...')\n",
    "    !git clone -q https://github.com/comfyanonymous/ComfyUI /content/ComfyUI\n",
    "    %cd /content/ComfyUI\n",
    "    !pip install -q -r requirements.txt\n",
    "    print('✅ ComfyUI installed!')\n",
    "else:\n",
    "    print('✅ ComfyUI already present, skipping.')\n",
    "\n",
    "# Create directories\n",
    "os.makedirs('/content/ComfyUI/output', exist_ok=True)\n",
    "os.makedirs('/content/ComfyUI/models/checkpoints', exist_ok=True)\n",
    "os.makedirs('/content/ComfyUI/models/diffusion_models', exist_ok=True)\n",
    "os.makedirs('/content/ComfyUI/models/text_encoders', exist_ok=True)\n",
    "os.makedirs('/content/ComfyUI/models/vae', exist_ok=True)\n",
    "\n",
    "# Clone VideoHelperSuite custom node for webm/video operations\n",
    "custom_nodes_dir = '/content/ComfyUI/custom_nodes'\n",
    "if not os.path.exists(os.path.join(custom_nodes_dir, 'ComfyUI-VideoHelperSuite')):\n",
    "    print('Cloning ComfyUI-VideoHelperSuite...')\n",
    "    !git clone -q https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite {custom_nodes_dir}/ComfyUI-VideoHelperSuite\n",
    "    print('✅ VideoHelperSuite installed!')\n",
    "else:\n",
    "    print('✅ VideoHelperSuite already present.')\n",
]))

# ── CELL 3: Download Models ──────────────────────────────────────────────
cells.append(make_markdown("## Cell 3 — Download AI Models (~15 GB, takes ~7 min)"))
cells.append(make_code([
    "# CELL 3: Download SDXL (AnythingXL) and Wan2.1 Models\n",
    "import os\n",
    "\n",
    "MODELS = {\n",
    "    '/content/ComfyUI/models/checkpoints/AnythingXL_xl.safetensors':\n",
    "        'https://civitai.com/api/download/models/384264?type=Model&format=SafeTensor',\n",
    "    '/content/ComfyUI/models/vae/sdxl_vae.safetensors':\n",
    "        'https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors',\n",
    "    '/content/ComfyUI/models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors':\n",
    "        'https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors',\n",
    "    '/content/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors':\n",
    "        'https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',\n",
    "    '/content/ComfyUI/models/vae/wan_2.1_vae.safetensors':\n",
    "        'https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors'\n",
    "}\n",
    "\n",
    "for path, url in MODELS.items():\n",
    "    if not os.path.exists(path):\n",
    "        print(f'Downloading {os.path.basename(path)}...')\n",
    "        !aria2c --console-log-level=error -c -x 16 -s 16 -k 1M \\\n",
    "            \"{url}\" \\\n",
    "            -d \"{os.path.dirname(path)}\" \\\n",
    "            -o \"{os.path.basename(path)}\"\n",
    "    else:\n",
    "        print(f'✅ {os.path.basename(path)} already downloaded.')\n",
    "\n",
    "# Verify\n",
    "print('\\nModel files status:')\n",
    "for path in MODELS.keys():\n",
    "    if os.path.exists(path):\n",
    "        size = os.path.getsize(path) / 1e9\n",
    "        print(f'  [FOUND] {os.path.basename(path)}  ({size:.2f} GB)')\n",
    "    else:\n",
    "        print(f'  [MISSING] {os.path.basename(path)}')\n",
]))

# ── CELL 4: Start ComfyUI ────────────────────────────────────────────────
cells.append(make_markdown("## Cell 4 — Start ComfyUI Server"))
cells.append(make_code([
    "# CELL 4: Start ComfyUI server in background\n",
    "import subprocess, time, urllib.request\n",
    "\n",
    "proc = subprocess.Popen(\n",
    "    ['python', 'main.py', '--listen', '0.0.0.0', '--port', '8188',\n",
    "     '--dont-print-server', '--disable-auto-launch'],\n",
    "    cwd='/content/ComfyUI',\n",
    "    stdout=subprocess.PIPE, stderr=subprocess.STDOUT\n",
    ")\n",
    "\n",
    "print('Waiting for ComfyUI to start...')\n",
    "for i in range(24):   # up to 2 minutes\n",
    "    time.sleep(5)\n",
    "    try:\n",
    "        urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=3)\n",
    "        print('✅ ComfyUI is ready!')\n",
    "        break\n",
    "    except:\n",
    "        print(f'  waiting... ({(i+1)*5}s)')\n",
    "else:\n",
    "    print('❌ ComfyUI failed to start! Check Cell 2 ran correctly.')\n",
]))

# ── CELL 5: Write drive_state.py ────────────────────────────────────────
cells.append(make_markdown("## Cell 5 — Write drive_state.py"))
cells.append(make_code(
    ["%%writefile /content/drive_state.py\n"] + drive_state_lines
))

# ── CELL 6: Write drive_worker.py ───────────────────────────────────────
cells.append(make_markdown("## Cell 6 — Write drive_worker.py"))
cells.append(make_code(
    ["%%writefile /content/drive_worker.py\n"] + drive_worker_lines
))

# ── CELL 7: Check & Initialize Drive ────────────────────────────────────
cells.append(make_markdown("## Cell 7 — Check Drive & Initialize Progress"))
cells.append(make_code([
    "# CELL 7: Verify Drive structure and create progress.json if needed\n",
    "import json, os, time\n",
    "\n",
    "DRIVE_ROOT = '/content/drive/MyDrive/AnimeFactory'\n",
    "\n",
    "# Create all required folders\n",
    "folders = [\n",
    "    'state/locks', 'inputs/tts', 'outputs/scenes', 'logs'\n",
    "]\n",
    "for f in folders:\n",
    "    os.makedirs(os.path.join(DRIVE_ROOT, f), exist_ok=True)\n",
    "print('✅ Folder structure ready')\n",
    "\n",
    "# Check master_script.json exists\n",
    "script_path = os.path.join(DRIVE_ROOT, 'state/master_script.json')\n",
    "if not os.path.exists(script_path):\n",
    "    print('❌ ERROR: master_script.json not found!')\n",
    "    print(f'   Upload it to: {script_path}')\n",
    "else:\n",
    "    with open(script_path) as f:\n",
    "        scenes = json.load(f)\n",
    "    print(f'✅ Script loaded: {len(scenes)} scenes')\n",
    "\n",
    "    # Check TTS files\n",
    "    tts_dir = os.path.join(DRIVE_ROOT, 'inputs/tts')\n",
    "    tts_files = [f for f in os.listdir(tts_dir) if f.endswith('.mp3')]\n",
    "    print(f'✅ TTS audio files: {len(tts_files)}/{len(scenes)} found')\n",
    "    if len(tts_files) < len(scenes):\n",
    "        print('⚠️  Missing audio! Run drive_uploader.py on your PC first.')\n",
    "\n",
    "    # Initialize progress.json if missing\n",
    "    progress_path = os.path.join(DRIVE_ROOT, 'state/progress.json')\n",
    "    if not os.path.exists(progress_path):\n",
    "        progress = {\n",
    "            'version': 1,\n",
    "            'total_scenes': len(scenes),\n",
    "            'scenes': {f'scene_{i+1:04d}': 'pending' for i in range(len(scenes))},\n",
    "            'updated_at': time.time()\n",
    "        }\n",
    "        with open(progress_path, 'w') as f:\n",
    "            json.dump(progress, f, indent=2)\n",
    "        print(f'✅ Initialized progress.json ({len(scenes)} scenes as pending)')\n",
    "    else:\n",
    "        with open(progress_path) as f:\n",
    "            p = json.load(f)\n",
    "        done = sum(1 for s in p['scenes'].values() if s == 'done')\n",
    "        print(f'✅ progress.json exists: {done}/{len(scenes)} scenes done')\n",
]))

# ── CELL 8: Run Worker ───────────────────────────────────────────────────
cells.append(make_markdown("## Cell 8 — 🚀 Run the Worker (Main Loop)"))
cells.append(make_code([
    "# CELL 8: Start the distributed worker loop\n",
    "# This will run until all scenes are done or the session expires.\n",
    "import sys\n",
    "sys.path.insert(0, '/content')\n",
    "\n",
    "DRIVE_ROOT = '/content/drive/MyDrive/AnimeFactory'\n",
    "COMFYUI_OUTPUT = '/content/ComfyUI/output'\n",
    "\n",
    "from drive_worker import run_worker\n",
    "run_worker(DRIVE_ROOT, COMFYUI_OUTPUT)\n",
]))

# ── CELL 9: Final Stitch ─────────────────────────────────────────────────
cells.append(make_markdown("## Cell 9 — 🎞️ Final Stitch (Run ONLY when all scenes are done)"))
cells.append(make_code([
    "# CELL 9: Stitch all completed scenes into final video\n",
    "import os, json, subprocess\n",
    "\n",
    "DRIVE_ROOT = '/content/drive/MyDrive/AnimeFactory'\n",
    "scenes_dir = os.path.join(DRIVE_ROOT, 'outputs', 'scenes')\n",
    "final_path = os.path.join(DRIVE_ROOT, 'outputs', 'final_video.mp4')\n",
    "\n",
    "scene_files = sorted([\n",
    "    os.path.join(scenes_dir, f)\n",
    "    for f in os.listdir(scenes_dir)\n",
    "    if f.endswith('.mp4')\n",
    "])\n",
    "\n",
    "print(f'Found {len(scene_files)} completed scenes')\n",
    "\n",
    "list_file = os.path.join(DRIVE_ROOT, 'outputs', 'concat_list.txt')\n",
    "with open(list_file, 'w') as f:\n",
    "    for sf in scene_files:\n",
    "        f.write(f\"file '{sf}'\\n\")\n",
    "\n",
    "print('Stitching final video...')\n",
    "subprocess.run([\n",
    "    'ffmpeg', '-y', '-f', 'concat', '-safe', '0',\n",
    "    '-i', list_file, '-c', 'copy', final_path\n",
    "], check=True)\n",
    "\n",
    "size = os.path.getsize(final_path) / 1e6\n",
    "print(f'✅ Final video saved: {final_path} ({size:.1f} MB)')\n",
]))

# ── Write notebook ───────────────────────────────────────────────────────
notebook = {
    "nbformat": 4,
    "nbformat_minor": 4,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10.0"},
        "accelerator": "GPU"
    },
    "cells": cells
}

out_path = "Colab_Distributed_Worker.ipynb"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"[OK] Notebook written: {out_path}")
print(f"     Cells: {len(cells)}")
print("     Upload to Colab and run cells 1 to 8 in order.")

