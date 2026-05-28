"""
=============================================================
  LOCAL PIPELINE — Image-Only with Ken Burns Effects
  Fully local: ComfyUI + TTS + FFmpeg on your PC.
=============================================================

Prerequisites:
  1. ComfyUI running locally on port 8188
  2. TTS server running: python tts_server.py (port 8765)
  3. FFmpeg in PATH
  4. Model downloaded: python download_model.py

Usage:
  python local_pipeline.py
  python local_pipeline.py --script my_story.json
  python local_pipeline.py --skip-tts       # if audio already generated
  python local_pipeline.py --skip-images    # if images already generated
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

# ===========================================================
# CONFIGURATION
# ===========================================================

COMFYUI_URL = "http://127.0.0.1:8000"
TTS_URL = "http://localhost:8765/tts"
COMFYUI_OUTPUT = os.path.join(
    os.path.expanduser("~"), "Documents", "ComfyUI", "output"
)

MODEL_NAME = "AnythingXL_xl.safetensors"
SCRIPT_FILE = "master_script.json"
OUTPUT_DIR = "output"

STYLE_PREFIX = (
    "manhwa style, webtoon art, sharp linework, vibrant colors, "
    "ultra detailed, masterpiece, best quality, "
)
NEGATIVE_PROMPT = (
    "low quality, worst quality, blurry, bad anatomy, bad proportions, "
    "deformed, ugly, 3d render, photorealistic, watermark, text, "
    "signature, extra limbs"
)

# 5 distinct voices — auto-assigned to characters
VOICE_POOL = [
    "en-US-GuyNeural",       # Deep male narrator (default)
    "en-US-AndrewNeural",    # Male hero
    "en-US-AriaNeural",      # Female
    "en-GB-RyanNeural",      # British / wise
    "en-US-DavisNeural",     # Villain / authority
]

# Ken Burns effects for cinematic motion on static images
KEN_BURNS_EFFECTS = [
    # Smooth zoom in (center) - very slow (reaches 1.5 in ~30s at 30fps)
    "z='min(zoom+0.0005,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # Smooth zoom out - very slow
    "z='if(eq(on,1),1.25,max(zoom-0.0005,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # Pan left to right with moderate zoom (z=1.2 gives 320px to pan)
    "z='1.2':x='min(on*0.3,iw-iw/zoom)':y='ih/2-(ih/zoom/2)'",
    # Pan right to left with moderate zoom
    "z='1.2':x='max((iw-iw/zoom)-on*0.3,0)':y='ih/2-(ih/zoom/2)'",
    # Zoom in + drift right slowly
    "z='min(zoom+0.0005,1.4)':x='min(iw/2+on*0.3,iw-iw/zoom)':y='ih/2-(ih/zoom/2)'",
    # Zoom in focusing on upper area (face level)
    "z='min(zoom+0.0005,1.5)':x='iw/2-(iw/zoom/2)':y='max(ih/3-(ih/zoom/2),0)'",
]


# ===========================================================
# HELPERS
# ===========================================================

def api_post(url, data, timeout=300):
    """POST JSON to a URL, return parsed response."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [ERROR] POST {url} failed: {e}")
        return None


def api_get(url, timeout=30):
    """GET JSON from a URL."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_prerequisites(skip_images=False, skip_tts=False):
    """Verify required services are available (only checks what's needed)."""
    errors = []

    # Check ComfyUI (only if generating images)
    if not skip_images:
        result = api_get(f"{COMFYUI_URL}/system_stats")
        if not result:
            errors.append(
                "ComfyUI is not running on port 8188.\n"
                "  Start it first, then re-run this script."
            )

    # Check TTS (only if generating audio)
    if not skip_tts:
        try:
            with urllib.request.urlopen("http://localhost:8765/", timeout=5) as r:
                pass
        except Exception:
            errors.append(
                "TTS server is not running on port 8765.\n"
                "  Run: python tts_server.py"
            )

    # Check FFmpeg (always needed for merge/stitch)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        errors.append(
            "FFmpeg not found in PATH.\n"
            "  Install from: https://ffmpeg.org/download.html"
        )

    # Check model (only if generating images)
    if not skip_images:
        ckpt_dir = os.path.join(
            os.path.expanduser("~"), "Documents", "ComfyUI", "models", "checkpoints"
        )
        model_path = os.path.join(ckpt_dir, MODEL_NAME)
        if not os.path.exists(model_path) or os.path.getsize(model_path) < 1e9:
            errors.append(
                f"Model not found: {MODEL_NAME}\n"
                "  Run: python download_model.py"
            )

    if errors:
        print("=" * 50)
        print("  PREREQUISITE CHECK FAILED")
        print("=" * 50)
        for e in errors:
            print(f"\n  [X] {e}")
        print()
        sys.exit(1)

    print("[OK] All prerequisites met")


# ===========================================================
# VOICE ASSIGNMENT
# ===========================================================

def assign_voices(scenes, custom_voice_map=None):
    """
    Auto-assign up to 5 voices to unique characters.
    Returns a dict: { "Narrator": "en-US-GuyNeural", ... }
    """
    speakers = []
    for s in scenes:
        spk = s.get("speaker") or s.get("character") or "Narrator"
        if spk not in speakers:
            speakers.append(spk)

    voice_map = {}
    if custom_voice_map:
        voice_map.update(custom_voice_map)

    assigned_count = len(voice_map)
    for spk in speakers:
        if spk not in voice_map:
            voice_map[spk] = VOICE_POOL[assigned_count % len(VOICE_POOL)]
            assigned_count += 1

    print(f"\n[VOICES] Assigned {len(voice_map)} characters:")
    for spk, voice in voice_map.items():
        print(f"  {spk:20s} -> {voice}")

    return voice_map


# ===========================================================
# TTS GENERATION
# ===========================================================

def generate_single_tts(i, scene, voice_map, tts_dir):
    """Worker function to generate TTS for a single scene."""
    scene_id = f"scene_{i+1:04d}"
    text = scene.get("story_text") or scene.get("narration") or scene.get("scene_text") or scene.get("text") or ""
    # Add dialogue to narration if present
    dialogue = scene.get("dialogue")
    if dialogue and dialogue != "null":
        if isinstance(dialogue, dict):
            dialogue = " ".join(str(v) for v in dialogue.values())
        elif isinstance(dialogue, list):
            dialogue = " ".join(str(v) for v in dialogue)
        else:
            dialogue = str(dialogue)
        text = text + " " + dialogue
    speaker = scene.get("speaker") or scene.get("character") or "Narrator"
    voice = voice_map.get(speaker, VOICE_POOL[0])

    out_path = os.path.join(tts_dir, f"{scene_id}.mp3")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"  [{scene_id}] Already exists, skipping")
        return True

    if not text:
        print(f"  [{scene_id}] No text, skipping")
        return False

    for attempt in range(3):
        try:
            resp = api_post(TTS_URL, {
                "text": text,
                "voice": voice,
                "filename": f"{scene_id}.mp3"
            }, timeout=60)

            if resp and resp.get("success"):
                # TTS server saves to its own tts_output dir; copy to our output
                src = resp.get("file_path", "")
                if os.path.exists(src):
                    shutil.copy2(src, out_path)
                print(f"  [{scene_id}] OK ({voice})")
                return True
            else:
                print(f"  [{scene_id}] FAILED (attempt {attempt+1}): {resp}")
        except Exception as e:
            print(f"  [{scene_id}] Error (attempt {attempt+1}): {e}")
        time.sleep(2)
    return False


def generate_tts(scenes, voice_map, tts_dir):
    """Generate TTS audio for all scenes in parallel."""
    os.makedirs(tts_dir, exist_ok=True)
    print(f"\n[TTS] Generating audio for {len(scenes)} scenes in parallel...")

    max_workers = min(10, len(scenes))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_single_tts, i, scene, voice_map, tts_dir): i
            for i, scene in enumerate(scenes)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"  [scene_{i+1:04d}] TTS generation thread failed with: {exc}")

    count = len([f for f in os.listdir(tts_dir) if f.endswith(".mp3")])
    print(f"[TTS] Done: {count}/{len(scenes)} audio files ready")


# ===========================================================
# IMAGE GENERATION via ComfyUI
# ===========================================================

def generate_image(prompt, scene_id, images_dir, neg_prompt=None, seed=None):
    """Generate a manhwa image via ComfyUI API."""
    # Only prepend STYLE_PREFIX if this isn't a Gemini-crafted prompt
    # (Gemini prompts already contain quality tags like 'masterpiece')
    if 'masterpiece' in prompt.lower() or 'best quality' in prompt.lower():
        full_prompt = prompt
    else:
        full_prompt = STYLE_PREFIX + prompt
    
    # Use per-scene negative prompt from Gemini, or fall back to default
    neg = neg_prompt if neg_prompt else NEGATIVE_PROMPT
    
    # Use consistency seed if provided, otherwise random
    img_seed = seed if seed else random.randint(1, 2**32)
    
    unique_prefix = scene_id

    workflow = {
        "1": {
            "inputs": {"ckpt_name": MODEL_NAME},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": full_prompt, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {"text": neg, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {"width": 1344, "height": 768, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": img_seed,
                "steps": 25,
                "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0], "positive": ["2", 0],
                "negative": ["3", 0], "latent_image": ["4", 0]
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

    print(f"  [IMG] Queuing {scene_id}...")
    result = api_post(f"{COMFYUI_URL}/prompt", {"prompt": workflow})

    if not result or "prompt_id" not in result:
        print(f"  [IMG] FAILED to queue {scene_id}")
        if result:
            print(f"        Response: {json.dumps(result)[:300]}")
        return None

    prompt_id = result["prompt_id"]
    print(f"  [IMG] Queued (ID: {prompt_id}), waiting...")

    # Poll until done
    for tick in range(180):  # up to 15 min
        time.sleep(5)
        history = api_get(f"{COMFYUI_URL}/history/{prompt_id}")
        if history and prompt_id in history:
            elapsed = (tick + 1) * 5
            print(f"  [IMG] ComfyUI finished in {elapsed}s")
            break
    else:
        print(f"  [IMG] TIMEOUT waiting for {scene_id}")
        return None

    # Find the output file
    for f in sorted(os.listdir(COMFYUI_OUTPUT), reverse=True):
        if f.startswith(unique_prefix) and f.endswith(".png"):
            src = os.path.join(COMFYUI_OUTPUT, f)
            dst = os.path.join(images_dir, f"{scene_id}.png")
            shutil.copy2(src, dst)
            print(f"  [IMG] Saved: {scene_id}.png")
            return dst

    print(f"  [IMG] No output file found for {scene_id}")
    return None


def generate_image_with_retry(prompt, scene_id, images_dir, neg_prompt=None, seed=None, retries=3):
    """Helper function to retry image generation if ComfyUI times out or fails."""
    for attempt in range(retries):
        try:
            path = generate_image(prompt, scene_id, images_dir, neg_prompt=neg_prompt, seed=seed)
            if path and os.path.exists(path) and os.path.getsize(path) > 10000:
                return path
            print(f"  [IMG] Attempt {attempt+1}/{retries} failed to yield a valid image. Retrying in 5s...")
        except Exception as e:
            print(f"  [IMG] Attempt {attempt+1}/{retries} raised exception: {e}. Retrying in 5s...")
        time.sleep(5)
    return None


def generate_all_images(scenes, images_dir):
    """Generate images for all scenes."""
    os.makedirs(images_dir, exist_ok=True)
    print(f"\n[IMAGES] Generating {len(scenes)} images via ComfyUI...")

    results = {}
    for i, scene in enumerate(scenes):
        scene_id = f"scene_{i+1:04d}"
        dst = os.path.join(images_dir, f"{scene_id}.png")

        if os.path.exists(dst) and os.path.getsize(dst) > 10000:
            print(f"  [{scene_id}] Already exists, skipping")
            results[scene_id] = dst
            continue

        prompt = scene.get("image_prompt") or scene.get("visual_prompt") or scene.get("text") or scene.get("scene_text") or scene.get("story_text") or ""
        if not prompt:
            print(f"  [{scene_id}] No visual prompt, skipping")
            continue

        neg_prompt = scene.get("negative_prompt")
        seed = scene.get("seed")
        path = generate_image_with_retry(prompt, scene_id, images_dir, neg_prompt=neg_prompt, seed=seed)
        if path:
            results[scene_id] = path
        else:
            print(f"  [WARNING] [{scene_id}] Image generation failed. Attempting fallback to previous scene's image...")
            # Look for the previous scene image
            fallback_found = False
            for prev_idx in range(i - 1, -1, -1):
                prev_id = f"scene_{prev_idx+1:04d}"
                prev_path = os.path.join(images_dir, f"{prev_id}.png")
                if os.path.exists(prev_path) and os.path.getsize(prev_path) > 10000:
                    shutil.copy2(prev_path, dst)
                    results[scene_id] = dst
                    print(f"  [IMG] Fallback SUCCESS: Copied {prev_id}.png to {scene_id}.png")
                    fallback_found = True
                    break
            if not fallback_found:
                print(f"  [ERROR] [{scene_id}] Image generation failed and no fallback image is available!")

    print(f"[IMAGES] Done: {len(results)}/{len(scenes)} images generated")
    return results


# ===========================================================
# KEN BURNS + AUDIO MERGE
# ===========================================================

def merge_scene(image_path, audio_path, output_path):
    """
    Merge a static image + audio into a cinematic video clip
    with a random Ken Burns effect (zoom/pan/slide).
    """
    effect = random.choice(KEN_BURNS_EFFECTS)

    # Get exact audio duration to avoid rendering unused zoompan frames
    try:
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path
        ]
        duration_str = subprocess.run(probe_cmd, capture_output=True, text=True, check=True).stdout.strip()
        frames = int(float(duration_str) * 30) + 30 # 1 sec buffer
    except Exception:
        frames = 1200 # fallback to 40 sec

    # Scale to 4K (3840x2160) intermediate canvas, apply zoompan, crop, and output 1080p
    filter_str = (
        f"[0:v]scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan={effect}:d={frames}:s=1920x1080:fps=30,"
        f"format=yuv420p[v]; "
        f"[1:a]areverse,silenceremove=start_periods=1:start_duration=0:start_threshold=-50dB,"
        f"areverse,silenceremove=start_periods=1:start_duration=0:start_threshold=-50dB[a]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-filter_complex", filter_str,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        size_mb = os.path.getsize(output_path) / 1e6
        print(f"  [MERGE] OK ({size_mb:.1f} MB)")
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[:500]
        print(f"  [MERGE] FAILED: {stderr}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  [MERGE] TIMEOUT (>10 min)")
        return False


def merge_single_scene(i, scene, images_dir, tts_dir, scenes_dir):
    """Worker function to merge a single scene's image and audio."""
    scene_id = f"scene_{i+1:04d}"
    image_path = os.path.join(images_dir, f"{scene_id}.png")
    audio_path = os.path.join(tts_dir, f"{scene_id}.mp3")
    output_path = os.path.join(scenes_dir, f"{scene_id}.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"  [{scene_id}] Already exists, skipping")
        return scene_id, output_path

    if not os.path.exists(image_path):
        print(f"  [{scene_id}] Missing image, skipping")
        return scene_id, None
    if not os.path.exists(audio_path):
        print(f"  [{scene_id}] Missing audio, skipping")
        return scene_id, None

    print(f"  [{scene_id}] Merging image + audio...")
    if merge_scene(image_path, audio_path, output_path):
        # Verify the file is not corrupted (e.g. missing moov atom)
        verify_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", output_path]
        try:
            subprocess.run(verify_cmd, check=True, capture_output=True)
            return scene_id, output_path
        except subprocess.CalledProcessError:
            print(f"  [{scene_id}] CORRUPTED FILE DETECTED! Deleting...")
            if os.path.exists(output_path):
                os.remove(output_path)
            return scene_id, None
    return scene_id, None


def merge_all_scenes(scenes, images_dir, tts_dir, scenes_dir):
    """Merge all image+audio pairs into scene videos in parallel."""
    os.makedirs(scenes_dir, exist_ok=True)
    print(f"\n[MERGE] Creating {len(scenes)} scene videos with Ken Burns effects in parallel...")

    cpu_count = os.cpu_count() or 4
    max_workers = max(1, min(2, cpu_count // 2)) # Cap at 2 to avoid overloading CPU
    print(f"  [INFO] Using {max_workers} parallel workers for FFmpeg merging...")

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(merge_single_scene, i, scene, images_dir, tts_dir, scenes_dir): i
            for i, scene in enumerate(scenes)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                scene_id, out_path = future.result()
                if out_path:
                    results[scene_id] = out_path
            except Exception as exc:
                print(f"  [scene_{i+1:04d}] Merge thread failed with: {exc}")

    print(f"[MERGE] Done: {len(results)}/{len(scenes)} scene clips ready")
    return results


# ===========================================================
# FINAL STITCH
# ===========================================================

def stitch_final(scenes_dir, output_path):
    """Concatenate all scene clips into one final video."""
    scene_files = sorted([
        os.path.join(scenes_dir, f)
        for f in os.listdir(scenes_dir)
        if f.endswith(".mp4") and os.path.getsize(os.path.join(scenes_dir, f)) > 10000
    ])

    if not scene_files:
        print("[STITCH] No scene clips found!")
        return None

    print(f"\n[STITCH] Combining {len(scene_files)} clips...")

    # Write concat list
    list_path = os.path.join(scenes_dir, "concat_list.txt")
    with open(list_path, "w") as f:
        for sf in scene_files:
            # FFmpeg concat needs forward slashes or escaped backslashes
            safe_path = os.path.abspath(sf).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        size_mb = os.path.getsize(output_path) / 1e6
        print(f"[STITCH] Final video: {output_path} ({size_mb:.1f} MB)")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"[STITCH] FAILED: {e.stderr.decode()[:300]}")
        return None


# ===========================================================
# MAIN
# ===========================================================

def main():
    parser = argparse.ArgumentParser(description="Local Manhwa Video Pipeline")
    parser.add_argument("--script", default=SCRIPT_FILE,
                        help="Path to master_script.json")
    parser.add_argument("--skip-tts", action="store_true",
                        help="Skip TTS generation (use existing audio)")
    parser.add_argument("--skip-images", action="store_true",
                        help="Skip image generation (use existing images)")
    parser.add_argument("--skip-merge", action="store_true",
                        help="Skip scene merging")
    parser.add_argument("--no-stitch", action="store_true",
                        help="Don't create final stitched video")
    args = parser.parse_args()

    # Load script
    if not os.path.exists(args.script):
        print(f"[ERROR] Script not found: {args.script}")
        sys.exit(1)

    with open(args.script, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Support both v2 format (raw array) and v3 format (object with 'scenes' key)
    if isinstance(payload, list):
        scenes = payload
        project_name = "Manhwa Project"
        custom_voice_map = None
    else:
        scenes = payload.get("scenes", [])
        project_name = payload.get("project_name") or payload.get("title") or "Manhwa Project"
        custom_voice_map = payload.get("voice_map")

    if not scenes:
        print("[ERROR] No scenes found in script file!")
        sys.exit(1)

    print("=" * 55)
    print("  LOCAL MANHWA PIPELINE")
    print(f"  Project: {project_name}")
    print(f"  Scenes: {len(scenes)}")
    print(f"  Output: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 55)

    # Check prerequisites
    check_prerequisites(skip_images=args.skip_images, skip_tts=args.skip_tts)

    # Directories
    tts_dir = os.path.join(OUTPUT_DIR, "tts")
    images_dir = os.path.join(OUTPUT_DIR, "images")
    scenes_dir = os.path.join(OUTPUT_DIR, "scenes")
    final_path = os.path.join(OUTPUT_DIR, "final_video.mp4")

    # Step 1: Voice assignment
    voice_map = assign_voices(scenes, custom_voice_map)

    # Step 2: TTS
    if not args.skip_tts:
        generate_tts(scenes, voice_map, tts_dir)
    else:
        print("\n[TTS] Skipped (--skip-tts)")

    # Step 3: Images
    if not args.skip_images:
        generate_all_images(scenes, images_dir)
    else:
        print("\n[IMAGES] Skipped (--skip-images)")

    # Step 4: Merge (image + audio -> scene clips)
    if not args.skip_merge:
        merge_all_scenes(scenes, images_dir, tts_dir, scenes_dir)
    else:
        print("\n[MERGE] Skipped (--skip-merge)")

    # Step 5: Final stitch
    if not args.no_stitch:
        stitch_final(scenes_dir, final_path)
    else:
        print("\n[STITCH] Skipped (--no-stitch)")

    print("\n" + "=" * 55)
    print("  PIPELINE COMPLETE!")
    print(f"  Scene clips:  {os.path.abspath(scenes_dir)}")
    print(f"  Final video:  {os.path.abspath(final_path)}")
    print("=" * 55)


if __name__ == "__main__":
    main()
