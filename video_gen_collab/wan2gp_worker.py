"""
=============================================================
  WAN2GP WORKER — Batch Video Generator for Colab/Kaggle
  Replaces the old ComfyUI-based drive_worker.py
=============================================================

Uses Wan2GP (deepbeepmeep/Wan2GP) as the video generation backend.
Wan2GP is faster, uses less VRAM, and supports multiple models
(Wan 2.1, LTX-2, Hunyuan) from a single codebase.

Flow:
  1. Connects to Wan2GP's Gradio server (running on same machine)
  2. Claims next scene from Google Drive state
  3. Generates video via Wan2GP API
  4. Merges with pre-generated TTS audio via FFmpeg
  5. Saves atomically to Drive (.tmp → .mp4)

Usage (from Colab cell):
  !python wan2gp_worker.py --drive-path /content/drive/MyDrive/AnimeFactory
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_state import DriveState


# ===========================================================
# CONFIGURATION
# ===========================================================

WAN2GP_DIR = "/content/Wan2GP"
WAN2GP_OUTPUT = "/content/Wan2GP/outputs"
WAN2GP_URL = "http://127.0.0.1:7860"

# Character consistency block — prepended to EVERY scene prompt.
# Edit this to match your story's protagonist.
CHARACTER_BLOCK = (
    "consistent character, same person throughout, "
    "young Korean man, 22 years old, sharp jawline, "
    "dark swept-back hair, intense dark eyes, lean muscular build, "
)

# Style prefix for anime/manhwa look
STYLE_PREFIX = (
    "manhwa style, webtoon art, sharp linework, vibrant colors, "
    "cinematic lighting, ultra detailed, masterpiece, best quality, "
)

NEGATIVE_PROMPT = (
    "low quality, worst quality, blurry, bad anatomy, bad proportions, "
    "deformed, ugly, watermark, text, signature, extra limbs, "
    "static image, frozen, no motion"
)

# Model selection: "wan21" or "ltx2"
DEFAULT_MODEL = "wan21"

# Video settings
VIDEO_WIDTH = 832
VIDEO_HEIGHT = 480
VIDEO_FRAMES = 81       # ~5 seconds at 16fps
VIDEO_STEPS = 20        # Lower = faster, 20 is good quality/speed tradeoff
VIDEO_CFG = 6.0
VIDEO_FPS = 16


# ===========================================================
# WAN2GP GENERATION (via Gradio Client)
# ===========================================================

def wait_for_wan2gp():
    """Wait briefly to check if Wan2GP Gradio server is responding."""
    import urllib.request
    print("[WORKER] Checking if Wan2GP server is active...")
    for i in range(3):  # Check 3 times (15 seconds total)
        try:
            urllib.request.urlopen(WAN2GP_URL, timeout=3)
            print("[WORKER] ✅ Wan2GP server is ready!")
            return True
        except Exception:
            if i < 2:
                time.sleep(5)
    print("[WORKER] ⚠️ Wan2GP server not responding. Will run in headless mode.")
    return False


def _model_type_for(model):
    """Map worker model key to Wan2GP model_type string."""
    if model == "ltx2":
        return "ltx2"
    return "t2v_1.3B"


def _build_wan2gp_settings(prompt, model, output_name):
    """Build a Wan2GP settings JSON payload for `wgp.py --process`."""
    return {
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        "video_length": VIDEO_FRAMES,
        "num_inference_steps": VIDEO_STEPS,
        "guidance_scale": VIDEO_CFG,
        "model_type": _model_type_for(model),
        "output_filename": f"{output_name}.mp4",
        "repeat_generation": 1,
        "batch_size": 1,
    }


def generate_video_wan2gp(prompt, output_name, model=DEFAULT_MODEL):
    """
    Generate a video using Wan2GP CLI mode (`wgp.py --process settings.json`).
    
    Returns: path to generated .mp4 file, or None on failure.
    """
    full_prompt = CHARACTER_BLOCK + STYLE_PREFIX + prompt
    output_path = os.path.join(WAN2GP_OUTPUT, f"{output_name}.mp4")

    settings_path = os.path.join(WAN2GP_OUTPUT, f"{output_name}_settings.json")
    os.makedirs(WAN2GP_OUTPUT, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(_build_wan2gp_settings(full_prompt, model, output_name), f, indent=2)

    cmd = [
        sys.executable, "wgp.py",
        "--process", settings_path,
        "--output-dir", WAN2GP_OUTPUT,
    ]
    if model == "ltx2":
        pass  # model_type is set in settings JSON
    else:
        cmd.append("--t2v-1-3B")
    
    print(f"  [VIDEO] Generating {output_name} with {model} (headless)...")
    print(f"  [VIDEO] Prompt: {prompt[:80]}...")
    
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=WAN2GP_DIR,
            timeout=600,  # 10 minute timeout
            capture_output=True,
            text=True
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode != 0:
            print(f"  [VIDEO] ❌ Generation failed ({elapsed:.0f}s)")
            print(f"  [VIDEO] stderr: {result.stderr[:500]}")
            return None
        
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / 1024 / 1024
            print(f"  [VIDEO] ✅ Generated in {elapsed:.0f}s ({size_mb:.1f} MB)")
            return output_path
        
        # Check for output in default locations
        for f in os.listdir(WAN2GP_OUTPUT):
            if f.startswith(output_name) and f.endswith(".mp4"):
                found = os.path.join(WAN2GP_OUTPUT, f)
                print(f"  [VIDEO] ✅ Found at {found} ({elapsed:.0f}s)")
                return found
        
        print(f"  [VIDEO] ❌ No output file found after {elapsed:.0f}s")
        return None
        
    except subprocess.TimeoutExpired:
        print(f"  [VIDEO] ❌ Generation timed out (600s)")
        return None
    except Exception as e:
        print(f"  [VIDEO] ❌ Error: {e}")
        return None


def generate_video_gradio(prompt, output_name, model=DEFAULT_MODEL):
    """
    Generate video via Wan2GP's Gradio API.
    """
    try:
        from gradio_client import Client
    except ImportError:
        print("  [VIDEO] gradio_client not installed, installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gradio_client"],
                      check=True, capture_output=True)
        from gradio_client import Client
    
    full_prompt = CHARACTER_BLOCK + STYLE_PREFIX + prompt
    
    print(f"  [VIDEO] Generating via Gradio API: {output_name}...")
    
    try:
        client = Client(WAN2GP_URL)
        
        # Submit generation request
        result = client.predict(
            full_prompt,           # prompt
            NEGATIVE_PROMPT,       # negative prompt
            VIDEO_WIDTH,           # width
            VIDEO_HEIGHT,          # height
            VIDEO_FRAMES,          # num frames
            VIDEO_STEPS,           # steps
            VIDEO_CFG,             # cfg scale
            api_name="/generate"
        )
        
        if result and os.path.exists(str(result)):
            # Copy to our output location
            output_path = os.path.join(WAN2GP_OUTPUT, f"{output_name}.mp4")
            import shutil
            shutil.copy2(str(result), output_path)
            print(f"  [VIDEO] ✅ Generated via Gradio: {output_path}")
            return output_path
        
        print(f"  [VIDEO] ❌ Gradio returned no result")
        return None
        
    except Exception as e:
        print(f"  [VIDEO] ❌ Gradio error: {e}")
        return None


def generate_video(prompt, output_name, model=DEFAULT_MODEL):
    """
    Try Gradio API first (keeps model in VRAM for speed), fall back to headless.
    """
    # 1. Try Gradio API if server is responsive
    import urllib.request
    server_active = False
    try:
        urllib.request.urlopen(WAN2GP_URL, timeout=2)
        server_active = True
    except Exception:
        pass

    if server_active:
        print("  [VIDEO] Wan2GP server is active. Calling Gradio API...")
        result = generate_video_gradio(prompt, output_name, model)
        if result:
            return result
        print("  [VIDEO] Gradio API call failed. Falling back to headless mode...")
    else:
        print("  [VIDEO] Wan2GP server not responding. Using headless mode...")

    # 2. Fallback to headless command-line execution
    return generate_video_wan2gp(prompt, output_name, model)


# ===========================================================
# SCENE PROCESSING
# ===========================================================

def resolve_prompt(scene_data, scene_type):
    """Extract the best prompt from scene data based on type."""
    if scene_type == "video":
        return (
            scene_data.get("video_prompt")
            or scene_data.get("visual_prompt")
            or scene_data.get("image_prompt")
            or scene_data.get("text")
            or scene_data.get("story_text")
            or ""
        )
    else:
        return (
            scene_data.get("image_prompt")
            or scene_data.get("visual_prompt")
            or scene_data.get("text")
            or scene_data.get("story_text")
            or ""
        )


def merge_video_audio(video_path, audio_path, output_path):
    """
    Merge generated video with TTS audio using FFmpeg.
    Scales video to 1080p, loops/trims to match audio length.
    """
    command = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",      # Loop video if shorter than audio
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex",
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
            "format=yuv420p[final]",
        "-map", "[final]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ]
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, timeout=120)
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"  [MERGE] ✅ {size_mb:.1f} MB")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [MERGE] ❌ FFmpeg failed: {e.stderr.decode()[:300]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  [MERGE] ❌ FFmpeg timed out")
        return False


def process_scene(scene_info, state, model=DEFAULT_MODEL):
    """
    Process a single scene end-to-end:
    1. Resolve prompt from scene data
    2. Generate video via Wan2GP
    3. Merge with pre-generated TTS audio
    4. Return path to merged .tmp file
    """
    scene_id = scene_info["id"]
    scene_data = scene_info["data"]
    scene_type = scene_data.get("type", "video")  # Default to video now
    
    # Get prompt
    prompt = resolve_prompt(scene_data, scene_type)
    if not prompt:
        print(f"  [ERROR] No prompt found for {scene_id}")
        return None
    
    # Check TTS audio exists
    audio_path = os.path.join(state.tts_dir, f"{scene_id}.mp3")
    if not os.path.exists(audio_path):
        print(f"  [ERROR] Missing TTS: {audio_path}")
        return None
    
    # Generate video
    video_path = generate_video(prompt, scene_id, model)
    if not video_path:
        return None
    
    # Merge video + audio
    tmp_output = os.path.join(state.scenes_dir, f"{scene_id}.tmp")
    if merge_video_audio(video_path, audio_path, tmp_output):
        return tmp_output
    
    return None


# ===========================================================
# MAIN WORKER LOOP
# ===========================================================

def run_worker(drive_path, model=DEFAULT_MODEL, max_scenes=None):
    """
    Main worker loop. Claims and processes scenes until done.
    """
    worker_id = f"wan2gp_{uuid.uuid4().hex[:8]}"
    state = DriveState(drive_path)
    
    print(f"\n{'='*60}")
    print(f"  WAN2GP DISTRIBUTED WORKER: {worker_id}")
    print(f"  Drive: {drive_path}")
    print(f"  Model: {model}")
    print(f"  Video: {VIDEO_WIDTH}x{VIDEO_HEIGHT}, {VIDEO_FRAMES} frames")
    print(f"{'='*60}\n")
    
    # Ensure output directory
    os.makedirs(WAN2GP_OUTPUT, exist_ok=True)
    
    # Wait for Wan2GP
    if not wait_for_wan2gp():
        print("[WORKER] Attempting headless-only mode (no server needed)...")
    
    # Clean up stale locks from crashed workers
    state.cleanup_stale()
    state.get_summary()
    
    scenes_processed = 0
    
    while True:
        if max_scenes and scenes_processed >= max_scenes:
            print(f"\n[WORKER] Reached limit of {max_scenes} scenes.")
            break
        
        # Claim next scene
        scene_info = state.claim_next_scene(worker_id)
        if not scene_info:
            print("\n[WORKER] ✅ No more scenes. Worker complete!")
            break
        
        scene_id = scene_info["id"]
        print(f"\n{'='*50}")
        print(f"  Scene: {scene_id}")
        print(f"  Type: {scene_info['data'].get('type', 'video')}")
        print(f"  Text: {scene_info['data'].get('text', '')[:80]}...")
        print(f"{'='*50}")
        
        try:
            tmp_output = process_scene(scene_info, state, model)
            
            if tmp_output and os.path.exists(tmp_output):
                state.complete_scene(scene_id, tmp_output)
                scenes_processed += 1
            else:
                state.fail_scene(scene_id)
        
        except KeyboardInterrupt:
            print(f"\n[WORKER] Interrupted! Releasing {scene_id}...")
            state.fail_scene(scene_id)
            break
        
        except Exception as e:
            print(f"\n[WORKER] Error on {scene_id}: {e}")
            state.fail_scene(scene_id)
            continue
    
    # Final summary
    state.get_summary()
    print(f"\n[WORKER] {worker_id} processed {scenes_processed} scenes. Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wan2GP Distributed Worker")
    parser.add_argument("--drive-path", type=str, required=True,
                        help="Path to AnimeFactory on mounted Drive")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        choices=["wan21", "ltx2"],
                        help="Video model to use (default: wan21)")
    parser.add_argument("--max-scenes", type=int, default=None,
                        help="Max scenes to process (optional)")
    
    args = parser.parse_args()
    run_worker(args.drive_path, args.model, args.max_scenes)
