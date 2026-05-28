"""
=============================================================
  THE DAILY ORCHESTRATOR
  The heart of the AI Video Factory.
=============================================================

What this script does:
  1. Reads the master_script.json (your Groq-generated story)
  2. Picks up where it left off (using progress.json)
  3. For each scene:
     - Generates audio via TTS Server (port 8765)
     - Generates visuals via ComfyUI API (port 8188)
       → type:"video" = Wan2.1 video generation
       → type:"image" = AnythingXL image generation
     - Merges them together with FFmpeg (sync_video_audio.py)
  4. Saves progress so you can stop and resume tomorrow

How to run:
  python orchestrator.py generate          ← Processes the next daily batch
  python orchestrator.py generate --limit 5  ← Process only 5 scenes (for testing)
  python orchestrator.py stitch            ← Stitches all daily chunks into final video
  python orchestrator.py status            ← Shows current progress
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
import urllib.parse

# ===========================================================
# CONFIGURATION — Edit these paths if needed
# ===========================================================
BASE_DIR = r"C:\Users\prana\OneDrive\Desktop\reels"
COMFYUI_OUTPUT = r"C:\Users\prana\Documents\ComfyUI\output"
SCRIPT_FILE = os.path.join(BASE_DIR, "master_script.json")
STATE_FILE = os.path.join(BASE_DIR, "n8n", "output", "progress.json")
SCENES_DIR = os.path.join(BASE_DIR, "n8n", "output", "scenes")
CHUNKS_DIR = os.path.join(BASE_DIR, "n8n", "output", "chunks")
FINAL_DIR = os.path.join(BASE_DIR, "n8n", "output", "final")
REMOTE_DOWNLOADS_DIR = os.path.join(BASE_DIR, "n8n", "output", "remote_downloads")

TTS_URL = "http://localhost:8765/tts"
COMFYUI_URL = "http://127.0.0.1:8000"

# Remote mode: set to True when using Google Colab GPU
# Set COLAB_URL to the cloudflared tunnel URL from your Colab notebook
REMOTE_MODE = False
COLAB_URL = ""  # e.g. "https://abc-123.trycloudflare.com"

# Voice assignments for multi-character TTS
VOICE_MAP = {
    "Narrator":    "en-GB-RyanNeural",
    "Hero":        "en-US-GuyNeural",
    "Villain":     "en-US-SteffanNeural",
    "Female":      "en-US-AriaNeural",
    "default":     "en-US-GuyNeural",
}

# Manhwa style prefix for all image generation prompts
STYLE_PREFIX = "manhwa style, webtoon art, sharp linework, vibrant colors, ultra detailed, masterpiece, best quality, "
NEGATIVE_PROMPT = "low quality, worst quality, blurry, bad anatomy, bad proportions, deformed, ugly, 3d render, photorealistic, watermark, text, signature, extra limbs"

# ===========================================================
# HELPER FUNCTIONS
# ===========================================================

def ensure_dirs():
    """Create all necessary output directories."""
    for d in [SCENES_DIR, CHUNKS_DIR, FINAL_DIR, REMOTE_DOWNLOADS_DIR, os.path.join(BASE_DIR, "tts_output")]:
        os.makedirs(d, exist_ok=True)

def get_comfyui_url():
    """Returns the active ComfyUI URL (local or remote Colab)."""
    if REMOTE_MODE and COLAB_URL:
        return COLAB_URL
    return COMFYUI_URL


def api_post(url, data):
    """
    Send a JSON POST request and return the parsed response.
    This is a simple wrapper around urllib so we don't need 'requests'.
    """
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [ERROR] API call to {url} failed: {e}")
        return None


def api_get(url):
    """Send a GET request and return the parsed response."""
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [ERROR] GET {url} failed: {e}")
        return None


# ===========================================================
# PHASE 1: TTS GENERATION
# ===========================================================

def generate_tts(text, speaker, scene_num):
    """
    Sends text to the TTS server and returns the path to the audio file.
    
    How it works:
      1. Looks up the speaker name in VOICE_MAP to find the right voice.
      2. Sends an HTTP POST request to tts_server.py (port 8765).
      3. tts_server.py uses edge-tts to generate an MP3 file.
      4. Returns the file path where the MP3 was saved.
    """
    voice = VOICE_MAP.get(speaker, VOICE_MAP["default"])
    filename = f"scene_{scene_num:04d}.mp3"
    
    payload = {
        "text": text,
        "voice": voice,
        "rate": "+5%",       # Slightly faster for dramatic pacing
        "filename": filename
    }
    
    print(f"  [TTS] Generating audio for scene {scene_num} (voice: {voice})...")
    result = api_post(TTS_URL, payload)
    
    if result and result.get("success"):
        print(f"  [TTS] Saved: {result['file_path']}")
        return result["file_path"]
    else:
        print(f"  [TTS] FAILED for scene {scene_num}")
        return None


# ===========================================================
# PHASE 2: IMAGE GENERATION (ComfyUI + AnythingXL)
# ===========================================================

def generate_image(prompt, scene_num):
    """
    Sends a prompt to ComfyUI to generate a manhwa-style image.
    
    How it works:
      1. Builds a ComfyUI API-format JSON workflow (the same structure
         as AnythingXL_Manhwa_Workflow.json, but with a dynamic prompt).
      2. POSTs it to ComfyUI's /prompt endpoint.
      3. Polls ComfyUI's /history endpoint until the job is done.
      4. Returns the path to the saved image.
    
    The API format is different from the UI format:
      - UI format has 'nodes' and 'links' (what you see when you drag-drop).
      - API format is a flat dictionary where each key is a node ID
        and connections use ["node_id", output_index] syntax.
    """
    full_prompt = STYLE_PREFIX + prompt
    unique_prefix = f"scene_{scene_num:04d}"
    
    # This is the API-format workflow (same nodes as the drag-drop JSON,
    # but structured for programmatic use)
    workflow = {
        "1": {
            "inputs": {"ckpt_name": "AnythingXL_xl.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": full_prompt, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {"text": NEGATIVE_PROMPT, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {"width": 1216, "height": 832, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": random.randint(1, 2**32),
                "steps": 25,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "6": {
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {"filename_prefix": unique_prefix, "images": ["6", 0]},
            "class_type": "SaveImage"
        }
    }
    
    print(f"  [IMG] Generating image for scene {scene_num}...")
    url = get_comfyui_url()
    result = api_post(f"{url}/prompt", {"prompt": workflow})
    
    if not result or "prompt_id" not in result:
        print(f"  [IMG] FAILED to queue scene {scene_num}")
        return None
    
    prompt_id = result["prompt_id"]
    return wait_for_comfyui(prompt_id, unique_prefix, "image")


# ===========================================================
# PHASE 3: VIDEO GENERATION (ComfyUI + Wan2.1)
# ===========================================================

def generate_video(prompt, scene_num, part=1, fps=None):
    """
    Sends a prompt to ComfyUI to generate a video clip using Wan2.1.
    
    How it works:
      1. Builds a ComfyUI API-format JSON workflow using the Wan2.1
         model nodes (UNETLoader, CLIPLoader, VAELoader, etc.).
      2. POSTs it to ComfyUI's /prompt endpoint.
      3. Polls /history until the video is done (~3 minutes).
      4. Returns the path to the saved video (WEBM animation).
    
    Key difference from image generation:
      - Uses UNETLoader (diffusion_models) instead of CheckpointLoaderSimple.
      - Uses CLIPLoader with type "wan" instead of the checkpoint's built-in CLIP.
      - Uses EmptyHunyuanLatentVideo (which has width, height, LENGTH, batch).
      - Output is an animated WEBM file, not a static PNG.
    """
    unique_prefix = f"video_{scene_num:04d}_p{part}"
    
    # Wan2.1 negative prompt (Chinese text from the official workflow)
    wan_negative = "low quality, worst quality, blurry, static, distorted, 3d render, photorealistic, ugly"
    
    # Enforce manhwa/anime style for the video just like the images
    full_prompt = STYLE_PREFIX + prompt
    
    workflow = {
        "37": {
            "inputs": {
                "unet_name": "wan2.1_t2v_1.3B_fp16.safetensors",
                "weight_dtype": "default"
            },
            "class_type": "UNETLoader"
        },
        "38": {
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default"
            },
            "class_type": "CLIPLoader"
        },
        "39": {
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
            "class_type": "VAELoader"
        },
        "48": {
            "inputs": {"model": ["37", 0], "shift": 8},
            "class_type": "ModelSamplingSD3"
        },
        "6": {
            "inputs": {"text": full_prompt, "clip": ["38", 0]},
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {"text": wan_negative, "clip": ["38", 0]},
            "class_type": "CLIPTextEncode"
        },
        "40": {
            "inputs": {"width": 832, "height": 480, "length": 81 if REMOTE_MODE else 33, "batch_size": 1},
            "class_type": "EmptyHunyuanLatentVideo"
        },
        "3": {
            "inputs": {
                "seed": random.randint(1, 2**32),
                "steps": 30,
                "cfg": 6.0,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["48", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["40", 0]
            },
            "class_type": "KSampler"
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["39", 0]},
            "class_type": "VAEDecode"
        },
        "28": {
            "inputs": {
                "filename_prefix": unique_prefix,
                "codec": "vp9",
                "fps": fps if fps else (16 if REMOTE_MODE else 8),
                "crf": 32,
                "images": ["8", 0]
            },
            "class_type": "SaveWEBM"
        }
    }
    
    mode_label = "REMOTE/Colab" if REMOTE_MODE else "LOCAL"
    print(f"  [VIDEO] Generating video for scene {scene_num} [{mode_label}] (this takes ~3-5 min)...")
    url = get_comfyui_url()
    result = api_post(f"{url}/prompt", {"prompt": workflow})
    
    if not result or "prompt_id" not in result:
        print(f"  [VIDEO] FAILED to queue scene {scene_num}")
        return None
    
    prompt_id = result["prompt_id"]
    return wait_for_comfyui(prompt_id, unique_prefix, "video")


# ===========================================================
# COMFYUI POLLING — Wait for generation to complete
# ===========================================================

def wait_for_comfyui(prompt_id, prefix, gen_type):
    """
    Polls ComfyUI's /history endpoint until the given prompt_id
    shows up as completed. Then retrieves the output file.
    
    LOCAL MODE:  Reads output directly from the local ComfyUI output folder.
    REMOTE MODE: Downloads the file over HTTP from the Colab ComfyUI server.
    """
    max_wait = 900 if REMOTE_MODE else 600  # 15 min remote, 10 min local
    elapsed = 0
    url = get_comfyui_url()
    
    while elapsed < max_wait:
        time.sleep(5)
        elapsed += 5
        
        history = api_get(f"{url}/history/{prompt_id}")
        if history and prompt_id in history:
            print(f"  [DONE] ComfyUI finished in {elapsed}s")
            
            # --- REMOTE MODE: Download via ComfyUI /view API ---
            if REMOTE_MODE:
                return download_from_comfyui(history, prompt_id, prefix, gen_type)
            
            # --- LOCAL MODE: Read from local disk ---
            break
    else:
        print(f"  [TIMEOUT] ComfyUI took too long for {prefix}")
        return None
    
    # LOCAL MODE: Find the output file on disk
    matching_files = []
    for f in os.listdir(COMFYUI_OUTPUT):
        if f.startswith(prefix) and not f.endswith(".webp"):
            full_path = os.path.join(COMFYUI_OUTPUT, f)
            matching_files.append(full_path)
            
    if matching_files:
        matching_files.sort(key=os.path.getmtime, reverse=True)
        newest_file = matching_files[0]
        print(f"  [FOUND] Output: {newest_file}")
        return newest_file
    
    print(f"  [ERROR] Could not find output file starting with {prefix}")
    return None


def download_from_comfyui(history, prompt_id, prefix, gen_type):
    """
    Downloads a generated file from a remote ComfyUI instance.
    ComfyUI stores output info in /history — we extract the filename
    and download it via the /view endpoint.
    """
    url = get_comfyui_url()
    
    try:
        outputs = history[prompt_id]["outputs"]
        # Walk through all output nodes to find our file
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img_info in node_output["images"]:
                    filename = img_info["filename"]
                    subfolder = img_info.get("subfolder", "")
                    file_type = img_info.get("type", "output")
                    
                    if filename.startswith(prefix):
                        # Build the download URL
                        download_url = (f"{url}/view?"
                                        f"filename={urllib.parse.quote(filename)}"
                                        f"&subfolder={urllib.parse.quote(subfolder)}"
                                        f"&type={file_type}")
                        
                        local_path = os.path.join(REMOTE_DOWNLOADS_DIR, filename)
                        print(f"  [DOWNLOAD] Fetching {filename} from Colab...")
                        
                        urllib.request.urlretrieve(download_url, local_path)
                        file_size = os.path.getsize(local_path)
                        print(f"  [DOWNLOAD] Saved {file_size / 1024:.0f} KB → {local_path}")
                        return local_path
    except Exception as e:
        print(f"  [ERROR] Failed to download from ComfyUI: {e}")
    
    print(f"  [ERROR] Could not find output file {prefix} in history")
    return None


# ===========================================================
# PHASE 4: MERGE AUDIO + VIDEO (FFmpeg)
# ===========================================================

def merge_scene(visual_path, audio_path, scene_num):
    """
    Calls sync_video_audio.py to merge the visual and audio into
    a single video clip for this scene.
    
    The sync script handles two cases:
      - If visual_path is an image (.png/.jpg) → applies Ken Burns zoom
      - If visual_path is a video (.webp/.mp4) → freezes last frame to match audio
    """
    output_path = os.path.join(SCENES_DIR, f"scene_{scene_num:04d}.mp4")
    sync_script = os.path.join(BASE_DIR, "sync_video_audio.py")
    
    print(f"  [MERGE] Combining scene {scene_num}...")
    
    cmd = [
        "python", sync_script,
        "--video", visual_path,
        "--audio", audio_path,
        "--output", output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  [MERGE] Saved: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  [MERGE] FAILED: {e.stderr.decode()}")
        return None


# ===========================================================
# THE MAIN DAILY LOOP
# ===========================================================

def load_state():
    """Load progress from disk, or create fresh state."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"completed_scenes": 0, "current_day": 1}


def save_state(state):
    """Save progress to disk."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def run_daily(limit=None):
    """
    The main function. Processes scenes from the master script.
    
    Flow:
      1. Load master_script.json
      2. Read progress.json to find where we left off
      3. Loop through scenes:
         a. Generate TTS audio
         b. Generate visual (image or video based on scene type)
         c. Merge them with FFmpeg
         d. Save progress after each scene (crash-safe!)
      4. After all scenes for today, combine into day_X_chunk.mp4
    """
    ensure_dirs()
    
    # Load the master script
    if not os.path.exists(SCRIPT_FILE):
        print(f"[ERROR] No master script found at {SCRIPT_FILE}")
        print("Run the Groq script generator first, or create a test script.")
        sys.exit(1)
    
    with open(SCRIPT_FILE, "r") as f:
        scenes = json.load(f)
    
    state = load_state()
    start = state["completed_scenes"]
    total = len(scenes)
    
    if start >= total:
        print("[COMPLETE] All scenes have been processed!")
        print("Run: python orchestrator.py stitch")
        return
    
    # Determine how many scenes to process today
    end = total if limit is None else min(start + limit, total)
    day = state["current_day"]
    
    print("=" * 60)
    print(f"DAY {day} — Processing scenes {start+1} to {end} of {total}")
    print("=" * 60)
    
    day_scene_files = []
    
    for i in range(start, end):
        scene = scenes[i]
        scene_num = i + 1
        
        print(f"\n--- Scene {scene_num}/{total} ---")
        print(f"  Type: {scene.get('type', 'image')}")
        print(f"  Speaker: {scene.get('speaker', 'Narrator')}")
        print(f"  Text: {scene.get('text', '')[:80]}...")
        
        # Step A: Generate audio
        audio_path = generate_tts(
            scene.get("text", ""),
            scene.get("speaker", "Narrator"),
            scene_num
        )
        if not audio_path:
            print(f"  [SKIP] Skipping scene {scene_num} (TTS failed)")
            continue
        
        # Step B: Generate visual
        visual_prompt = scene.get("visual_prompt", scene.get("text", ""))
        scene_type = scene.get("type", "image")
        
        if scene_type == "video":
            # Randomize FPS to balance pacing and total duration
            rand_val = random.random()
            if rand_val < 0.50:
                scene_fps = 24  # 50% chance
            elif rand_val < 0.85:
                scene_fps = 16  # 35% chance
            else:
                scene_fps = 8   # 15% chance
                
            print(f"  [VIDEO] Selected {scene_fps} FPS for scene {scene_num} pacing.")
            print(f"  [VIDEO] Generating video part 1 for scene {scene_num} (this takes ~3-5 min)...")
            visual_path_1 = generate_video(visual_prompt + ", wide shot, full body, environment visible", scene_num, part=1, fps=scene_fps)
            
            if not visual_path_1:
                print(f"  [SKIP] Skipping scene {scene_num} (visual generation failed on part 1)")
                continue
                
            print(f"  [VIDEO] Generating video part 2 for scene {scene_num} (this takes ~3-5 min)...")
            visual_path_2 = generate_video(visual_prompt + ", dramatic close up shot, detailed face", scene_num, part=2, fps=scene_fps)
            
            if not visual_path_2:
                print(f"  [SKIP] Skipping scene {scene_num} (visual generation failed on part 2)")
                continue
                
            print(f"  [VIDEO] Concatenating video parts for scene {scene_num}...")
            concat_path = os.path.join(SCENES_DIR, f"video_concat_{scene_num:04d}.webm")
            concat_txt = os.path.join(SCENES_DIR, f"concat_{scene_num:04d}.txt")
            
            with open(concat_txt, "w") as f:
                p1 = os.path.abspath(visual_path_1).replace('\\', '/')
                p2 = os.path.abspath(visual_path_2).replace('\\', '/')
                f.write(f"file '{p1}'\n")
                f.write(f"file '{p2}'\n")
            
            try:
                subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", concat_path], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
                visual_path = concat_path
            except subprocess.CalledProcessError:
                print(f"  [ERROR] Failed to concatenate videos for scene {scene_num}")
                continue
        else:
            visual_path = generate_image(visual_prompt, scene_num)
            if not visual_path:
                print(f"  [SKIP] Skipping scene {scene_num} (visual generation failed)")
                continue
        
        # Step C: Merge audio + visual
        merged_path = merge_scene(visual_path, audio_path, scene_num)
        if merged_path:
            day_scene_files.append(merged_path)
        
        # Step D: Save progress after every scene (crash-safe)
        state["completed_scenes"] = i + 1
        save_state(state)
        print(f"  [PROGRESS] {i+1}/{total} scenes complete")
    
    # Combine all today's scenes into a daily chunk
    if day_scene_files:
        chunk_path = os.path.join(CHUNKS_DIR, f"day_{day:02d}_chunk.mp4")
        concat_videos(day_scene_files, chunk_path)
        state["current_day"] += 1
        save_state(state)
        print(f"\n[DAY {day} COMPLETE] Saved to: {chunk_path}")
    
    remaining = total - state["completed_scenes"]
    if remaining > 0:
        print(f"\n{remaining} scenes remaining. Run again tomorrow!")
    else:
        print(f"\n[ALL DONE] All {total} scenes processed!")
        print("Run: python orchestrator.py stitch")


# ===========================================================
# PHASE 5: FINAL STITCHER
# ===========================================================

def concat_videos(file_list, output_path):
    """
    Concatenates a list of video files into one using FFmpeg.
    
    How it works:
      1. Creates a temporary text file listing all input videos.
      2. Tells FFmpeg to read that list and concatenate them.
      3. The 'concat' demuxer is lossless — it doesn't re-encode.
    """
    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for vf in file_list:
            # FFmpeg concat requires forward slashes and escaped paths
            safe_path = vf.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        os.remove(list_file)
        print(f"  [CONCAT] Saved: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"  [CONCAT FAILED] {e.stderr.decode()}")


def stitch_final():
    """
    Stitches all daily chunks into the final 1-hour video.
    Optionally adds background music underneath.
    """
    ensure_dirs()
    
    chunks = sorted([
        os.path.join(CHUNKS_DIR, f)
        for f in os.listdir(CHUNKS_DIR)
        if f.endswith(".mp4")
    ])
    
    if not chunks:
        print("[ERROR] No daily chunks found. Run 'generate' first.")
        return
    
    print(f"[STITCH] Found {len(chunks)} daily chunks")
    for c in chunks:
        print(f"  - {os.path.basename(c)}")
    
    final_path = os.path.join(FINAL_DIR, "final_video.mp4")
    concat_videos(chunks, final_path)
    
    print("\n" + "=" * 60)
    print(f"FINAL VIDEO READY: {final_path}")
    print("=" * 60)
    print("Upload this to YouTube!")


def show_status():
    """Show current progress."""
    state = load_state()
    
    if os.path.exists(SCRIPT_FILE):
        with open(SCRIPT_FILE, "r") as f:
            total = len(json.load(f))
    else:
        total = "?"
    
    done = state.get("completed_scenes", 0)
    day = state.get("current_day", 1)
    
    print(f"Day:              {day}")
    print(f"Scenes completed: {done}/{total}")
    if isinstance(total, int) and total > 0:
        pct = round(done / total * 100, 1)
        print(f"Progress:         {pct}%")
    
    chunks = [f for f in os.listdir(CHUNKS_DIR) if f.endswith(".mp4")] if os.path.exists(CHUNKS_DIR) else []
    print(f"Daily chunks:     {len(chunks)}")


# ===========================================================
# ENTRY POINT
# ===========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Video Factory Orchestrator")
    parser.add_argument("command", choices=["generate", "stitch", "status"],
                        help="generate=process scenes, stitch=combine chunks, status=show progress")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max scenes to process (for testing, e.g. --limit 3)")
    parser.add_argument("--remote", action="store_true",
                        help="Use remote Colab GPU instead of local ComfyUI")
    parser.add_argument("--colab-url", type=str, default=None,
                        help="Cloudflared tunnel URL from your Colab notebook")
    
    args = parser.parse_args()
    
    # Activate remote mode if --remote flag is set
    if args.remote:
        REMOTE_MODE = True
        if args.colab_url:
            COLAB_URL = args.colab_url.rstrip("/")
        
        if not COLAB_URL:
            print("[ERROR] Remote mode requires a Colab URL!")
            print("  Usage: python orchestrator.py generate --remote --colab-url https://xxx.trycloudflare.com")
            sys.exit(1)
        
        print(f"[REMOTE MODE] Using Colab GPU at: {COLAB_URL}")
        print(f"  → Video length: 81 frames (5 seconds @ 16 FPS)")
        print(f"  → Images + videos will be downloaded over HTTP")
        print()
    
    if args.command == "generate":
        run_daily(args.limit)
    elif args.command == "stitch":
        stitch_final()
    elif args.command == "status":
        show_status()
