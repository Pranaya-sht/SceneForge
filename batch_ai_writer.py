"""
batch_ai_writer.py — Crash-Proof 80-Scene Manhwa Script Generator
100% FREE: Gemini (free) + Ollama (local) only.

Usage:
  python batch_ai_writer.py --input story.txt --scenes 80 --char "young Korean man, 22, sharp jawline..."
  python batch_ai_writer.py --resume progress_MyStory.json
"""
import argparse, json, os, re, sys, time, random, urllib.request, urllib.error

# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
ABLITERATE_MODEL = "huihui_ai/qwen2.5-abliterate:7b"
CODER_MODEL = "thirdeyeai/Qwen2.5-Coder-7B-Instruct-Uncensored:Q4_0"
BATCH_SIZE = 5
MAX_RETRIES = 5
RETRY_DELAY = 10

DEFAULT_ART = "manhwa webtoon korean comic style, clean precise linework, vibrant saturated colors, dramatic cinematic lighting, highly detailed digital illustration"
DEFAULT_NEG = "worst quality, low quality, blurry, bad anatomy, deformed, ugly, watermark, text, extra limbs, cropped, out of frame, duplicate, mutated, disfigured"

ADDICTIVE_PROMPT = """You are an expert content architect specializing in high-retention short-form YouTube Shorts and Reels. Your single goal is to make every word, sentence, and scene maximally addictive with hyper-fast pacing.

HOOK ARCHITECTURE: Open with a visceral question or bold claim. Drop micro-revelations and pattern interrupts every single sentence. No greetings, no warm-up. Start at the climax.

PSYCHOLOGICAL TRIGGERS: Embed dopamine reward loops, high-stakes loss aversion, and intense curiosity gaps. Every scene must end on a mini cliffhanger to force them to watch the next one.

TONE & PACING: Extremely fast-paced, aggressive, and punchy. Use short, rhythmic sentences. No filler words. If a sentence doesn't shock, escalate, or hook, CUT IT.

CRITICAL CONSTRAINT: Each scene MUST be extremely short. 10 to 40 words MAXIMUM per scene. This equals 2 to 15 seconds of audio. Do not exceed this limit."""

ADDICTIVE_VISUAL = """VISUAL DIRECTION FOR ADDICTIVE CONTENT:
- Faces and eyes in key frames — human gaze commands involuntary attention
- Use contrast and unexpected juxtaposition to trigger pattern-interrupt responses
- Every image must mirror the emotional beat — each image change is an emotional cue
- Frame compositions that create visual tension: dutch angles for unease, low angles for power, extreme close-ups for intimacy
- Color psychology: warm reds/golds for desire, cold blues for isolation, high contrast for danger
- Characters should show raw emotion in their expressions — the audience must FEEL what the character feels
- Dramatic lighting that creates mystery — half-lit faces, rim lighting, volumetric light shafts"""


def load_gemini_keys():
    """Load Gemini API keys from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    keys = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY"):
                    val = line.split("=", 1)[1].strip()
                    keys.extend([k.strip() for k in val.split(",") if k.strip()])
    if not keys:
        print("[ERROR] No GEMINI_API_KEY found in .env")
        sys.exit(1)
    return keys


def gemini_request(prompt, system="", keys=None, max_tokens=8000, temperature=0.7, response_schema=None):
    """Call Gemini 2.5 Flash via native v1beta generateContent API with exponential backoff."""
    allowed_max_tokens = min(max_tokens, 8192)
    
    for attempt in range(MAX_RETRIES):
        key = keys[attempt % len(keys)] if keys else keys[0]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
        
        # Build contents structure
        contents = [
            {
                "parts": [{"text": prompt}]
            }
        ]
        
        gen_config = {
            "temperature": temperature,
            "maxOutputTokens": allowed_max_tokens
        }
        
        if response_schema:
            gen_config["responseMimeType"] = "application/json"
            gen_config["responseSchema"] = response_schema
            
        body_dict = {
            "contents": contents,
            "generationConfig": gen_config
        }
        
        if system:
            body_dict["systemInstruction"] = {
                "parts": [{"text": system}]
            }
            
        body = json.dumps(body_dict).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                # Extract text from native Gemini response format
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                raise ValueError(f"Unexpected response structure: {data}")
        except urllib.error.HTTPError as e:
            err_details = e.fp.read().decode('utf-8', errors='ignore')
            print(f"  [GEMINI] Attempt {attempt+1}/{MAX_RETRIES} failed with HTTP {e.code}: {e.reason}")
            print(f"  [GEMINI] API Error Details: {err_details}")
            if attempt < MAX_RETRIES - 1:
                sleep_time = 5 * (2 ** attempt) + random.uniform(0, 2)
                print(f"  [WAIT] Waiting {sleep_time:.1f}s before retry...")
                time.sleep(sleep_time)
        except Exception as e:
            print(f"  [GEMINI] Attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                sleep_time = 5 * (2 ** attempt) + random.uniform(0, 2)
                print(f"  [WAIT] Waiting {sleep_time:.1f}s before retry...")
                time.sleep(sleep_time)
    raise RuntimeError("Gemini failed after all retries.")


def ollama_request(model, system, user_prompt, num_predict=4000, temperature=0.9):
    """Call local Ollama with crash recovery and exponential backoff."""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False,
        "options": {"temperature": temperature, "top_p": 0.95, "num_predict": num_predict, "repeat_penalty": 1.1}
    }).encode()

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
                content = data.get("message", {}).get("content", "") or data.get("response", "")
                if content.strip():
                    return content
                print(f"  [OLLAMA] Empty response, retrying...")
        except urllib.error.URLError as e:
            print(f"\n  [WARN] Ollama connection failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                sleep_time = RETRY_DELAY * (2 ** attempt) + random.uniform(0, 2)
                print(f"  [WAIT] Waiting {sleep_time:.1f}s before retry...")
                time.sleep(sleep_time)
            else:
                print("\n" + "="*60)
                print("  [ALERT] OLLAMA IS DOWN!")
                print("  Please restart it: ollama serve")
                print("  Then press ENTER to continue...")
                print("="*60)
                input()
                return ollama_request(model, system, user_prompt, num_predict, temperature)
        except Exception as e:
            print(f"  [OLLAMA] Error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                sleep_time = RETRY_DELAY * (2 ** attempt) + random.uniform(0, 2)
                print(f"  ⏳ Waiting {sleep_time:.1f}s before retry...")
                time.sleep(sleep_time)
    raise RuntimeError(f"Ollama ({model}) failed after all retries.")


# ═══════════════════════════════════════════
# PHASE 1: GEMINI SCENE BREAKDOWN
# ═══════════════════════════════════════════
def phase1_breakdown(story_text, num_scenes, keys):
    """Use Gemini to break story into scene beats."""
    print(f"\n{'='*55}")
    print(f"  PHASE 1: Gemini Scene Breakdown ({num_scenes} scenes)")
    print(f"{'='*55}")

    system = (
        f"You are a script supervisor. Read the script and identify exactly {num_scenes} scene beats.\n"
        "Output ONLY valid JSON - zero markdown, zero explanation:\n"
        '{"scenes":[{"n":1,"beat":"1 sentence what happens","setting":"where + time","emotion":"one word"}]}'
    )

    # For large stories, truncate to fit Gemini context
    max_chars = 50000
    if len(story_text) > max_chars:
        print(f"  [INFO] Story too long ({len(story_text)} chars), using first {max_chars} chars")
        story_text = story_text[:max_chars]

    schema = {
        "type": "OBJECT",
        "properties": {
            "scenes": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "n": {"type": "INTEGER"},
                        "beat": {"type": "STRING"},
                        "setting": {"type": "STRING"},
                        "emotion": {"type": "STRING"}
                    },
                    "required": ["n", "beat", "setting", "emotion"]
                }
            }
        },
        "required": ["scenes"]
    }

    raw = gemini_request(f"Identify {num_scenes} scene beats:\n\n{story_text}", system=system, keys=keys, max_tokens=num_scenes * 200, temperature=0.3, response_schema=schema)

    try:
        beats = json.loads(raw)["scenes"]
    except Exception as e:
        print(f"  [ERROR] JSON loading failed: {e}")
        print(f"  [DEBUG] Raw response was: {raw[:500]}...")
        # Direct fallback parse
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            beats = json.loads(m.group(0))["scenes"]
        else:
            raise RuntimeError("Gemini did not return valid JSON for scene breakdown.")

    print(f"  [OK] Got {len(beats)} scene beats from Gemini")
    return beats


# ═══════════════════════════════════════════
# PHASE 2: OLLAMA ABLITERATE (BATCHED)
# ═══════════════════════════════════════════
def phase2_expand(beats, char_desc, genre, progress):
    """Expand beats into vivid 150-word narrations using Abliterate, in batches."""
    expanded = progress.get("expanded", {})
    total = len(beats)
    done = len(expanded)

    print(f"\n{'='*55}")
    print(f"  PHASE 2: Abliterate Creative Expansion")
    print(f"  {done}/{total} already done, processing remaining...")
    print(f"{'='*55}")

    system = (
        f"{ADDICTIVE_PROMPT}\n\n"
        f"You are a master {genre} manhwa writer. Write with full creative freedom.\n"
        f"MAIN CHARACTER: {char_desc}\n"
        f"GENRE: {genre}\n\n"
        "Task: Expand each scene beat into a VERY SHORT 20-40 word vivid description.\n"
        "Include: what the reader SEES, what the character FEELS, ATMOSPHERE, DIALOGUE (1-2 lines), DRAMATIC TURNING POINT.\n"
        "Label each: SCENE X:\n[expansion]\n\nSCENE Y:\n[expansion]"
    )

    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        # Skip if all in this batch are done
        batch_indices = list(range(batch_start, batch_end))
        pending = [i for i in batch_indices if str(i) not in expanded]
        if not pending:
            continue

        batch_beats = [beats[i] for i in batch_indices]
        beats_text = "\n\n".join(
            f"SCENE {b.get('n', i+1)}: {b.get('beat', b.get('story_text', 'Beat'))}\n  Setting: {b.get('setting', 'unknown')}\n  Emotion: {b.get('emotion', 'dramatic')}"
            for i, b in zip(batch_indices, batch_beats)
        )

        print(f"\n  [BATCH] Expanding scenes {batch_start+1}-{batch_end} ({len(pending)} pending)...")
        result = ollama_request(ABLITERATE_MODEL, system, f"Expand these {len(batch_beats)} scene beats:\n\n{beats_text}", num_predict=BATCH_SIZE * 800)

        # Parse expanded scenes from result
        scene_blocks = re.split(r'SCENE\s+\d+\s*:', result)
        scene_blocks = [b.strip() for b in scene_blocks if b.strip()]

        for idx, block in zip(batch_indices, scene_blocks):
            expanded[str(idx)] = block
            print(f"    [OK] Scene {idx+1} expanded ({len(block)} chars)")

        # Auto-save progress
        progress["expanded"] = expanded
        save_progress(progress)
        print(f"  [SAVE] Progress saved ({len(expanded)}/{total} expanded)")

    return expanded


# ═══════════════════════════════════════════
# PHASE 3: OLLAMA CODER (BATCHED)
# ═══════════════════════════════════════════
def phase3_structure(beats, expanded, char_desc, genre, progress):
    """Convert expanded text into structured JSON using Coder, in batches."""
    structured = progress.get("structured", [])
    done_indices = {s.get("scene_number", 0) for s in structured}
    total = len(beats)

    print(f"\n{'='*55}")
    print(f"  PHASE 3: Coder JSON Structuring")
    print(f"  {len(structured)}/{total} already done...")
    print(f"{'='*55}")

    system = (
        "You are a JSON architect. Convert story prose into structured JSON.\n"
        "Output ONLY valid JSON - no markdown, no backticks.\n\n"
        "Required output:\n"
        '{"scenes":[{\n'
        '  "n": 1,\n'
        '  "title": "Short punchy title max 5 words",\n'
        '  "story_text": "max 15-40 words total (1-2 punchy sentences)",\n'
        '  "dialogue": "Most impactful line of dialogue or null",\n'
        '  "setting": "Location time of day atmosphere",\n'
        '  "emotion": "Primary emotion",\n'
        '  "action": "Key physical action",\n'
        '  "mood_tags": ["3 to 5 atmosphere tags"],\n'
        '  "colors": ["3 dominant colors"]\n'
        '}]}'
    )

    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_indices = list(range(batch_start, batch_end))
        pending = [i for i in batch_indices if (i + 1) not in done_indices]
        if not pending:
            continue

        combined_text = "\n\n".join(
            f"SCENE {i+1}:\n{expanded.get(str(i), beats[i].get('beat', ''))}"
            for i in batch_indices
        )

        print(f"\n  [BATCH] Structuring scenes {batch_start+1}-{batch_end}...")
        result = ollama_request(CODER_MODEL, system, f"Convert every scene to JSON:\n\n{combined_text}", num_predict=BATCH_SIZE * 600, temperature=0.1)

        # Extract JSON
        result = re.sub(r'```json\n?', '', result)
        result = re.sub(r'```\n?', '', result).strip()
        try:
            parsed = json.loads(result)
            scenes_list = parsed.get("scenes", [parsed] if "n" in parsed else [])
        except:
            m = re.search(r'\{[\s\S]*\}', result)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    scenes_list = parsed.get("scenes", [parsed])
                except:
                    print(f"    [WARN] Could not parse Coder output for batch {batch_start+1}-{batch_end}, using raw text")
                    scenes_list = []
            else:
                scenes_list = []

        # Fallback: if coder failed, create scene from expanded text directly
        for idx in batch_indices:
            scene_num = idx + 1
            if scene_num in done_indices:
                continue
            matched = next((s for s in scenes_list if s.get("n") == scene_num or s.get("scene_number") == scene_num), None)
            if not matched and scenes_list:
                local_idx = idx - batch_start
                matched = scenes_list[local_idx] if local_idx < len(scenes_list) else None

            if matched:
                matched["scene_number"] = scene_num
                structured.append(matched)
            else:
                # Fallback: build from expanded text + beat
                beat = beats[idx]
                structured.append({
                    "scene_number": scene_num,
                    "scene_title": beat.get("beat", f"Scene {scene_num}")[:50],
                    "story_text": expanded.get(str(idx), beat.get("beat", "")),
                    "dialogue": None,
                    "setting": beat.get("setting", "unknown"),
                    "emotion": beat.get("emotion", "dramatic"),
                    "action": "character reacts",
                    "mood_tags": ["tension", "drama"],
                    "colors": ["dark blue", "amber", "shadow black"]
                })
            done_indices.add(scene_num)
            print(f"    [OK] Scene {scene_num} structured")

        progress["structured"] = structured
        save_progress(progress)
        print(f"  [SAVE] Progress saved ({len(structured)}/{total} structured)")

    # Sort by scene number
    structured.sort(key=lambda s: s.get("scene_number", s.get("n", 0)))
    return structured


# ═══════════════════════════════════════════
# PHASE 4: GEMINI IMAGE PROMPTS
# ═══════════════════════════════════════════
def phase4_image_prompts(scenes, char_desc, art_style, keys):
    """Generate cinematic image prompts using Gemini AI with addictive visual psychology."""
    print(f"\n{'='*55}")
    print(f"  PHASE 4: Gemini AI Image Prompt Generation")
    print(f"{'='*55}")

    system = (
        f"{ADDICTIVE_VISUAL}\n\n"
        f"You are a concept artist for a {art_style} production.\n"
        f"MAIN CHARACTER: {char_desc}\n\n"
        "For each scene, write a highly detailed image generation prompt that captures:\n"
        "- Character pose, expression, and body language\n"
        "- Cinematic composition (camera angle, framing)\n"
        "- Lighting, atmosphere, weather\n"
        "- Color palette and mood\n"
        "- Narrative Literal: Explicitly describe EXACTLY what is happening in the scene based on the story text (who is doing what, specific actions, what objects are they interacting with). Do NOT just describe the mood.\n\n"
        "Output ONLY valid JSON:\n"
        '{"prompts":[{"n":1,"image_prompt":"detailed prompt...","negative_prompt":"bad quality...","video_prompt":"camera motion..."}]}'
    )

    seed = random.randint(100000, 999999)
    IMG_BATCH = 10  # Gemini can handle 10 scenes at once easily

    for batch_start in range(0, len(scenes), IMG_BATCH):
        batch_end = min(batch_start + IMG_BATCH, len(scenes))
        batch = scenes[batch_start:batch_end]

        # Skip if already has AI-generated image_prompt
        if all(s.get("image_prompt", "").startswith("masterpiece") == False and s.get("image_prompt") for s in batch):
            continue

        scenes_desc = "\n".join(
            f"SCENE {s.get('scene_number', i+1)}: {s.get('story_text', '')[:200]}\n  Setting: {s.get('setting', '')}\n  Emotion: {s.get('emotion', '')}\n  Action: {s.get('action', '')}\n  Colors: {', '.join(s.get('colors', s.get('color_palette', ['cinematic'])))}\n  Mood: {', '.join(s.get('mood_tags', ['dramatic']))}"
            for i, s in enumerate(batch)
        )

        schema = {
            "type": "OBJECT",
            "properties": {
                "prompts": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "n": {"type": "INTEGER"},
                            "image_prompt": {"type": "STRING"},
                            "negative_prompt": {"type": "STRING"},
                            "video_prompt": {"type": "STRING"}
                        },
                        "required": ["n", "image_prompt", "negative_prompt", "video_prompt"]
                    }
                }
            },
            "required": ["prompts"]
        }

        print(f"  [BATCH] Generating image prompts for scenes {batch_start+1}-{batch_end}...")
        try:
            raw = gemini_request(f"Write image prompts for these {len(batch)} scenes:\n\n{scenes_desc}", system=system, keys=keys, max_tokens=len(batch) * 400, temperature=0.7, response_schema=schema)
            try:
                prompts = json.loads(raw).get("prompts", [])
            except Exception as e:
                print(f"    [WARN] Direct JSON load failed, using fallback regex search: {e}")
                m = re.search(r'\{[\s\S]*\}', raw)
                prompts = json.loads(m.group(0)).get("prompts", []) if m else []

            for s, p in zip(batch, prompts):
                s["image_prompt"] = f"masterpiece, best quality, 8k, {art_style}, {char_desc}, " + p.get("image_prompt", "")
                s["negative_prompt"] = p.get("negative_prompt", DEFAULT_NEG)
                s["video_prompt"] = f"masterpiece, best quality, 8k, {art_style}, {char_desc}, " + p.get("video_prompt", f"Slow cinematic motion. {s.get('emotion', 'dramatic')} atmosphere.")
                print(f"    [OK] Scene {s.get('scene_number', '?')} prompt generated")
        except Exception as e:
            print(f"  [WARN] Gemini image prompts failed for batch: {e}")
            print(f"  [FALLBACK] Using mechanical prompts...")
            for s in batch:
                s["image_prompt"] = f"masterpiece, best quality, 8k, {art_style}, {char_desc}, {s.get('action', '')}, {s.get('setting', '')}, {s.get('emotion', '')} mood, cinematic lighting"
                s["negative_prompt"] = DEFAULT_NEG
                s["video_prompt"] = f"masterpiece, best quality, 8k, {art_style}, {char_desc}, " + f"Slow cinematic motion. {s.get('emotion', 'dramatic')} atmosphere."

    # Add rendering params to all scenes
    for i, scene in enumerate(scenes):
        scene.setdefault("negative_prompt", DEFAULT_NEG)
        scene["width"] = 1344
        scene["height"] = 768
        scene["steps"] = 25
        scene["cfg"] = 7.0
        scene["seed"] = seed + i

    print(f"  [OK] AI image prompts generated for {len(scenes)} scenes")
    return scenes


# ═══════════════════════════════════════════
# PROGRESS MANAGEMENT
# ═══════════════════════════════════════════
def get_progress_path(project_name):
    return os.path.join(os.path.dirname(__file__), f"progress_{project_name.replace(' ', '_')}.json")


def save_progress(progress):
    path = get_progress_path(progress["project_name"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def load_progress(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Crash-Proof Batch AI Manhwa Writer")
    parser.add_argument("--input", help="Path to .txt story file")
    parser.add_argument("--scenes", type=int, default=80, help="Number of scenes (default: 80)")
    parser.add_argument("--char", help="Character description")
    parser.add_argument("--genre", default="dark dramatic manhwa", help="Genre/tone")
    parser.add_argument("--art", default=DEFAULT_ART, help="Art style")
    parser.add_argument("--resume", help="Path to progress JSON to resume from")
    parser.add_argument("--project", default="", help="Project name")
    args = parser.parse_args()

    keys = load_gemini_keys()

    # Resume mode
    if args.resume:
        print(f"\n[RESUME] Loading progress from {args.resume}")
        progress = load_progress(args.resume)
        beats = progress["beats"]
        char_desc = progress["char_desc"]
        genre = progress["genre"]
        art_style = progress["art_style"]
        project_name = progress["project_name"]
    else:
        if not args.input:
            print("[ERROR] --input is required (path to .txt story file)")
            sys.exit(1)
        if not args.char:
            print("[ERROR] --char is required (character description)")
            sys.exit(1)
        if not os.path.exists(args.input):
            print(f"[ERROR] File not found: {args.input}")
            sys.exit(1)

        with open(args.input, "r", encoding="utf-8") as f:
            story_text = f.read()

        project_name = args.project or os.path.splitext(os.path.basename(args.input))[0]
        char_desc = args.char
        genre = args.genre
        art_style = args.art

        # Phase 1
        beats = phase1_breakdown(story_text, args.scenes, keys)

        progress = {
            "project_name": project_name,
            "char_desc": char_desc,
            "genre": genre,
            "art_style": art_style,
            "beats": beats,
            "expanded": {},
            "structured": []
        }
        save_progress(progress)

    # Phase 2
    expanded = phase2_expand(beats, char_desc, genre, progress)

    # Phase 3
    structured = phase3_structure(beats, expanded, char_desc, genre, progress)

    # Phase 4
    final_scenes = phase4_image_prompts(structured, char_desc, art_style, keys)

    # Save final output
    output_name = f"{project_name.replace(' ', '_')}_{len(final_scenes)}scenes.json"
    output_path = os.path.join(os.path.dirname(__file__), output_name)
    final_output = {
        "title": project_name,
        "project_name": project_name,
        "scenes": final_scenes
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    # Clean up progress file
    prog_path = get_progress_path(project_name)
    if os.path.exists(prog_path):
        os.remove(prog_path)

    print(f"\n{'='*55}")
    print(f"  [SUCCESS] SCRIPT GENERATION COMPLETE!")
    print(f"  Output: {output_path}")
    print(f"  Scenes: {len(final_scenes)}")
    print(f"\n  To render the video:")
    print(f"  python local_pipeline.py --script {output_name}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
