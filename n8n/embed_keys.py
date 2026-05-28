"""
FINAL REBUILD — auto_local_v3_configured.json
Fixes:
  - formTrigger typeVersion 2.2 -> 2.1 (compatible with n8n 2.17.7)
  - Injects addictive content system instruction into Abliterate + Gemini
  - All 7 previous bug fixes included
  - OpenRouter fallback chain included
  - API keys embedded
"""
import json

ADDICTIVE_STORY_INSTRUCTION = """You are an expert content architect specializing in high-retention short-form YouTube Shorts and Reels. Your single goal is to make every word, sentence, and scene maximally addictive with hyper-fast pacing.

HOOK ARCHITECTURE: Open with a visceral question or bold claim. Drop micro-revelations and pattern interrupts every single sentence. No greetings, no warm-up. Start at the climax.

PSYCHOLOGICAL TRIGGERS: Embed dopamine reward loops, high-stakes loss aversion, and intense curiosity gaps. Every scene must end on a mini cliffhanger to force them to watch the next one.

TONE & PACING: Extremely fast-paced, aggressive, and punchy. Use short, rhythmic sentences. No filler words. If a sentence doesn't shock, escalate, or hook, CUT IT.

CRITICAL CONSTRAINT: Each scene MUST be extremely short. 10 to 40 words MAXIMUM per scene. This equals 2 to 15 seconds of audio. Do not exceed this limit."""

ADDICTIVE_VISUAL_INSTRUCTION = """VISUAL DIRECTION FOR ADDICTIVE CONTENT:
- Faces and eyes in key frames — human gaze commands involuntary attention
- Use contrast and unexpected juxtaposition to trigger pattern-interrupt responses
- Every image must mirror the emotional beat — each image change is an emotional cue
- Frame compositions that create visual tension: dutch angles for unease, low angles for power, extreme close-ups for intimacy
- Color psychology: warm reds/golds for desire, cold blues for isolation, high contrast for danger
- Characters should show raw emotion in their expressions — the audience must FEEL what the character feels
- Dramatic lighting that creates mystery — half-lit faces, rim lighting, volumetric light shafts"""

# Load the original v3 (not the configured one, to start clean)
with open('n8n/auto_local_v3.json', 'r', encoding='utf-8') as f:
    flow = json.load(f)

import os

# Read keys from .env
env_keys = {}
env_path = '.env' if os.path.exists('.env') else 'n8n/.env'
with open(env_path, 'r', encoding='utf-8') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            env_keys[k.strip()] = v.strip().strip('"').strip("'")

# Map .env keys to our script keys
groq_env = env_keys.get('Groq_API_Key', '')
gemini_env = env_keys.get('Google_AI_Studio_API_Key', '') or env_keys.get('GEMINI_API_KEY', '').split(',')[0].strip()

# =============================================
# FIX ALL NODES
# =============================================
for node in flow['nodes']:

    # --- FIX: formTrigger version (the import error!) ---
    if node['type'] == 'n8n-nodes-base.formTrigger':
        node['typeVersion'] = 2.1  # 2.2 not supported in n8n 2.17.7
        # Make API key fields optional
        for field in node['parameters']['formFields']['values']:
            if "API Key" in field['fieldLabel']:
                field['requiredField'] = False
                field['placeholder'] = "(pre-configured - leave blank)"
        
        # Add Pre-built Scene JSON field after 'Script or Story Idea'
        fields = node['parameters']['formFields']['values']
        insert_idx = None
        for i, field in enumerate(fields):
            if field['fieldLabel'] == 'Script or Story Idea':
                field['requiredField'] = False  # Optional when JSON is provided
                insert_idx = i + 1
                break
        
        # Only add if not already present
        json_field_exists = any(f['fieldLabel'] == 'Pre-built Scene JSON' for f in fields)
        if insert_idx is not None and not json_field_exists:
            fields.insert(insert_idx, {
                'fieldLabel': 'Pre-built Scene JSON',
                'fieldType': 'textarea',
                'placeholder': '(Optional) Paste your full JSON from build_story.py here to skip AI scene breakdown.\nFormat: {"scenes":[...], "seed":123, ...}',
                'requiredField': False
            })

    # --- Prep node: inject keys + scale tokens ---
    if node['name'] == '\U0001f527 Prep + Build Groq Request':
        node['parameters']['jsCode'] = (
            "const f = $input.first().json;\n\n"
            "const projectName   = (f['Project Name']           || 'Story').trim();\n"
            "const charDesc      = (f['Character Description']  || '').trim();\n"
            "const rawScript     = (f['Script or Story Idea']   || '').trim();\n"
            "const sceneJson     = (f['Pre-built Scene JSON']   || '').trim();\n"
            "const genre         = (f['Genre and Tone']         || 'dark dramatic manhwa').trim();\n"
            "const rawStyle      = (f['Art Style']              || '').trim();\n"
            "const numScenes     = Math.max(1, parseInt(f['Number of Scenes']) || 8);\n"
            f"const groqKey       = (f['Groq API Key']           || '').trim() || '{groq_env}';\n"
            f"const aiStudioKey   = '{gemini_env}';\n\n"
            "if (!charDesc)  throw new Error('Character Description is required.');\n"
            "if (!rawScript && !sceneJson) throw new Error('Provide either a Script/Story OR Pre-built Scene JSON.');\n\n"
            "const artStyle = rawStyle ||\n"
            "  'manhwa webtoon korean comic style, clean precise linework, vibrant saturated colors, dramatic cinematic lighting, highly detailed digital illustration';\n\n"
            "// Check Pre-built Scene JSON field first, then fall back to Script field\n"
            "let preformattedScenes = null;\n"
            "let isComplete = false;\n"
            "let parsedProjectName = '';\n"
            "let parsedSeed = null;\n"
            "let parsedGenre = '';\n"
            "let parsedStyle = '';\n"
            "const jsonSource = sceneJson || rawScript;\n"
            "try {\n"
            "  const parsed = JSON.parse(jsonSource);\n"
            "  if (Array.isArray(parsed)) {\n"
            "    preformattedScenes = parsed;\n"
            "  } else if (parsed && typeof parsed === 'object') {\n"
            "    parsedProjectName = parsed.project_name || parsed.title || '';\n"
            "    parsedSeed = parsed.consistency_seed || parsed.seed || null;\n"
            "    parsedGenre = parsed.genre || '';\n"
            "    parsedStyle = parsed.art_style || parsed.style || '';\n"
            "    if (parsed.scenes && Array.isArray(parsed.scenes)) {\n"
            "      preformattedScenes = parsed.scenes;\n"
            "    } else {\n"
            "      const arrayKey = Object.keys(parsed).find(key => Array.isArray(parsed[key]));\n"
            "      if (arrayKey) preformattedScenes = parsed[arrayKey];\n"
            "    }\n"
            "  }\n"
            "  if (preformattedScenes && preformattedScenes.length > 0) {\n"
            "    const firstScene = preformattedScenes[0];\n"
            "    isComplete = !!(firstScene.image_prompt || firstScene.video_prompt || firstScene.visual_prompt);\n"
            "  }\n"
            "} catch(e) {}\n\n"
            "const finalNumScenes = preformattedScenes ? preformattedScenes.length : numScenes;\n"
            "const seed = parsedSeed !== null && !isNaN(parseInt(parsedSeed)) ? parseInt(parsedSeed) : (Math.floor(Math.random() * 999999) + 1);\n"
            "const maxTokens = Math.min(Math.max(finalNumScenes * 200, 4000), 32000);\n\n"
            "const groqSystem =\n"
            "  `You are a script supervisor. Read the script and identify exactly ${finalNumScenes} scene beats.\\n` +\n"
            "  `Output ONLY valid JSON - zero markdown, zero explanation:\\n` +\n"
            '  `{"scenes":[{"n":1,"beat":"1 sentence what happens","setting":"where + time","emotion":"one word"}]}`;\n\n'
            "return [{\n"
            "  json: {\n"
            "    projectName: parsedProjectName || projectName,\n"
            "    charDesc, rawScript,\n"
            "    genre: parsedGenre || genre,\n"
            "    artStyle: parsedStyle || artStyle,\n"
            "    numScenes: finalNumScenes,\n"
            "    groqKey, aiStudioKey, seed,\n"
            "    isPreformatted: !!preformattedScenes,\n"
            "    isComplete: isComplete,\n"
            "    preformattedScenes: preformattedScenes,\n"
            "    groqRequest: {\n"
            "      model: 'gemini-2.5-flash',\n"
            "      messages: [\n"
            "        { role: 'system', content: groqSystem },\n"
            "        { role: 'user',   content: `Identify ${finalNumScenes} scene beats:\\n\\n${rawScript}` }\n"
            "      ],\n"
            "      response_format: { type: 'json_object' },\n"
            "      temperature: 0.3,\n"
            "      max_tokens: maxTokens\n"
            "    }\n"
            "  }\n"
            "}];"
        )

    # --- Groq node -> Gemini node: rename and use Google OpenAI endpoint ---
    if node['name'] == '\u2460 xAI Grok \u2014 Scene Breakdown' or node['name'] == '\u2460 Groq \u2014 Scene Breakdown' or node['name'] == '\u2460 Gemini \u2014 Scene Breakdown':
        node['name'] = '\u2460 Gemini \u2014 Scene Breakdown'
        node['parameters']['url'] = "={{ $json.isPreformatted || $json.isComplete ? 'https://httpbin.org/post' : 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions' }}"
        
        # We also need to update the Authentication in this node to use the Gemini key instead of Groq key
        # In the expression for the Bearer token, we need to make sure it pulls the aiStudioKey
        for param in ['authentication', 'genericAuthType']:
            pass # Keep them as is, we just need to update the header value
        
        # Let's fix the header value in the node's parameters directly if it's set there
        if 'sendHeaders' in node['parameters'] and node['parameters']['sendHeaders']:
            for header in node['parameters']['headerParameters']['parameters']:
                if header['name'] == 'Authorization':
                    header['value'] = '=Bearer {{$json.aiStudioKey}}'

    # --- Ollama/OpenRouter/Gemini HTTP nodes: bypass if isComplete or isPreformatted ---
    if node['name'] == '② Ollama Abliterate — Creative Expand':
        node['parameters']['url'] = "={{ $json.isPreformatted || $json.isComplete ? 'https://httpbin.org/post' : 'http://host.docker.internal:11434/api/chat' }}"

    if node['name'] == '③ Ollama Coder — JSON Structure':
        node['parameters']['url'] = "={{ $json.isPreformatted || $json.isComplete ? 'https://httpbin.org/post' : 'http://host.docker.internal:11434/api/chat' }}"

    if node['name'] == '④ OpenRouter — Dialogue Polish':
        node['parameters']['url'] = "={{ $json.isPreformatted || $json.isComplete ? 'https://httpbin.org/post' : 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + $json.aiStudioKey }}"
        # Remove any OpenRouter auth headers since Gemini uses URL key auth
        if 'sendHeaders' in node['parameters']:
            node['parameters']['sendHeaders'] = False
        node['parameters'].pop('headerParameters', None)

    if node['name'] == '⑤ Gemini AI Studio — Image Prompts':
        node['parameters']['url'] = "={{ $json.isPreformatted || $json.isComplete ? 'https://httpbin.org/post' : 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + $json.aiStudioKey }}"

    # --- Parse Groq -> Abliterate: INJECT ADDICTIVE STORY INSTRUCTION ---
    if node['name'] == '\U0001f4ca Parse Groq \u2192 Build Abliterate':
        addictive_escaped = ADDICTIVE_STORY_INSTRUCTION.replace('\\', '\\\\').replace('`', '\\`').replace("'", "\\'").replace('\n', '\\n')
        
        node['parameters']['jsCode'] = (
            "const resp   = $input.first().json;\n"
            "const config = $('\U0001f527 Prep + Build Groq Request').first().json;\n\n"
            "if (config.isComplete || config.isPreformatted) {\n"
            "  return [{\n"
            "    json: {\n"
            "      ...config,\n"
            "      groqScenes: config.preformattedScenes,\n"
            "      abliterateRequest: {\n"
            "        model: 'huihui_ai/qwen2.5-abliterate:7b',\n"
            "        messages: [{ role: 'user', content: 'dummy' }],\n"
            "        options: { num_predict: 1 }\n"
            "      }\n"
            "    }\n"
            "  }];\n"
            "}\n\n"
            "let groqScenes;\n"
            "if (config.isPreformatted) {\n"
            "  groqScenes = config.preformattedScenes;\n"
            "} else {\n"
            "  if (!resp.choices?.[0]?.message?.content) {\n"
            "    throw new Error('Groq error: ' + JSON.stringify(resp).substring(0, 300));\n"
            "  }\n"
            "  const raw = resp.choices[0].message.content.replace(/```json\\n?/gi, '').replace(/```\\n?/g, '').trim();\n"
            "  try { groqScenes = JSON.parse(raw).scenes; }\n"
            "  catch {\n"
            "    const m = raw.match(/\\{[\\s\\S]*\\}/);\n"
            "    if (m) {\n"
            "      try { groqScenes = JSON.parse(m[0]).scenes; }\n"
            "      catch { throw new Error('Groq invalid JSON even after regex extraction. Length: ' + raw.length); }\n"
            "    } else {\n"
            "      throw new Error('Groq returned no JSON object. Length: ' + raw.length);\n"
            "    }\n"
            "  }\n"
            "}\n\n"
            "if (!Array.isArray(groqScenes) || !groqScenes.length) {\n"
            "  throw new Error('Groq returned no scenes.');\n"
            "}\n\n"
            "const beatsList = groqScenes.map(s => `SCENE ${s.n || s.scene_number || 1}: ${s.beat || s.story_text || s.scene_text || 'Beat'}\\n  Setting: ${s.setting || 'unknown'}\\n  Emotion: ${s.emotion || 'dramatic'}`).join('\\n\\n');\n\n"
            "const ablSystem =\n"
            f"  `{addictive_escaped}\\n\\n` +\n"
            "  `You are a master ${config.genre} manhwa writer. Write with full creative freedom - vivid, raw, emotional.\\n\\n` +\n"
            "  `MAIN CHARACTER: ${config.charDesc}\\n` +\n"
            "  `GENRE: ${config.genre}\\n\\n` +\n"
            "  `Task: Expand each scene beat into a VERY SHORT 20-40 word vivid description covering:\\n` +\n"
            "  ` What the reader SEES (composition, character pose, expression)\\n` +\n"
            "  ` What the character FEELS (internal state, physical sensation)\\n` +\n"
            "  ` ATMOSPHERE (lighting, weather, sounds)\\n` +\n"
            "  ` DIALOGUE (1-2 lines if natural)\\n` +\n"
            "  ` DRAMATIC TURNING POINT (what changes in this scene)\\n\\n` +\n"
            "  `Label each: SCENE 1:\\n[expansion]\\n\\nSCENE 2:\\n[expansion]`;\n\n"
            "return [{\n"
            "  json: {\n"
            "    ...config,\n"
            "    groqScenes,\n"
            "    abliterateRequest: {\n"
            "      model: 'huihui_ai/qwen2.5-abliterate:7b',\n"
            "      messages: [\n"
            "        { role: 'system', content: ablSystem },\n"
            "        { role: 'user',   content: `Expand these ${groqScenes.length} scene beats:\\n\\n${beatsList}` }\n"
            "      ],\n"
            "      stream: false,\n"
            "      options: { temperature: 0.92, top_p: 0.95, num_ctx: 8192, num_predict: Math.min(groqScenes.length * 800, 8192), repeat_penalty: 1.1 }\n"
            "    }\n"
            "  }\n"
            "}];"
        )

    # --- Parse Abliterate -> Coder: scale tokens and add isComplete bypass ---
    if node['name'] == '\U0001f4dd Parse Abliterate \u2192 Build Coder':
        node['parameters']['jsCode'] = (
            "const resp   = $input.first().json;\n"
            "const config = $('📊 Parse Groq → Build Abliterate').first().json;\n\n"
            "if (config.isComplete || config.isPreformatted) {\n"
            "  return [{\n"
            "    json: {\n"
            "      ...config,\n"
            "      expandedText: '',\n"
            "      coderRequest: {\n"
            "        model: 'thirdeyeai/Qwen2.5-Coder-7B-Instruct-Uncensored:Q4_0',\n"
            "        messages: [{ role: 'user', content: 'dummy' }],\n"
            "        options: { num_predict: 1 }\n"
            "      }\n"
            "    }\n"
            "  }];\n"
            "}\n\n"
            "const expandedText =\n"
            "  resp.message?.content || resp.response ||\n"
            "  (() => { throw new Error('Abliterate bad response: ' + JSON.stringify(resp).substring(0, 200)); })();\n\n"
            "if (expandedText.trim().length < 200) {\n"
            "  throw new Error('Abliterate returned too little — is the model loaded? Run: ollama run huihui_ai/qwen2.5-abliterate:7b');\n"
            "}\n\n"
            "const coderSystem =\n"
            "  `You are a JSON architect. Convert story prose into structured JSON.\\n` +\n"
            "  `Output ONLY valid JSON — no markdown, no backticks, nothing else.\\n\\n` +\n"
            "  `Required output:\\n` +\n"
            "  `{\"scenes\":[{\\n` +\n"
            "  `  \"n\": 1,\\n` +\n"
            "  `  \"title\": \"Short punchy title max 5 words\",\\n` +\n"
            "  `  \"story_text\": \"3 sentence summary of what happens\",\\n` +\n"
            "  `  \"dialogue\": \"Most impactful line of dialogue or null\",\\n` +\n"
            "  `  \"setting\": \"Location time of day atmosphere\",\\n` +\n"
            "  `  \"emotion\": \"Primary emotion\",\\n` +\n"
            "  `  \"action\": \"Key physical action\",\\n` +\n"
            "  `  \"mood_tags\": [\"3 to 5 atmosphere tags\"],\\n` +\n"
            "  `  \"colors\": [\"3 dominant colors\"]\\n` +\n"
            "  `}]}`;\n\n"
            "return [{\n"
            "  json: {\n"
            "    ...config,\n"
            "    expandedText,\n"
            "    coderRequest: {\n"
            "      model: 'thirdeyeai/Qwen2.5-Coder-7B-Instruct-Uncensored:Q4_0',\n"
            "      messages: [\n"
            "        { role: 'system', content: coderSystem },\n"
            "        { role: 'user',   content: `Convert every scene in this text to JSON. Output ONLY the JSON object:\\n\\n${expandedText}` }\n"
            "      ],\n"
            "      stream: false,\n"
            "      format: 'json',\n"
            "      options: { temperature: 0.1, top_p: 0.85, num_ctx: 8192, num_predict: Math.min(expandedText.length, 8192) }\n"
            "    }\n"
            "  }\n"
            "}];"
        )

    # --- Parse Coder -> Build OpenRouter ---
    if node['name'] == '\U0001f4cb Parse Coder \u2192 Build OpenRouter':
        node['parameters']['jsCode'] = (
            "const resp   = $input.first().json;\n"
            "const config = $('📝 Parse Abliterate → Build Coder').first().json;\n\n"
            "if (config.isComplete) {\n"
            "  const normScenes = config.preformattedScenes.map((s, i) => ({\n"
            "    n:          s.n || s.scene_number || (i + 1),\n"
            "    title:      s.title || s.scene_title || `Scene ${i + 1}`,\n"
            "    story_text: s.story_text || s.scene_text || '',\n"
            "    dialogue:   s.dialogue !== undefined ? s.dialogue : null,\n"
            "    setting:    s.setting    || 'unknown',\n"
            "    emotion:    s.emotion    || s.primary_emotion || 'dramatic',\n"
            "    action:     s.action     || s.action_beat || '',\n"
            "    mood_tags:  Array.isArray(s.mood_tags) ? s.mood_tags : ['cinematic'],\n"
            "    colors:     Array.isArray(s.colors) ? s.colors :\n"
            "                Array.isArray(s.color_palette) ? s.color_palette : ['dark blue','gold','shadow'],\n"
            "    image_prompt: s.image_prompt || null,\n"
            "    negative_prompt: s.negative_prompt || null,\n"
            "    video_prompt: s.video_prompt || null\n"
            "  }));\n\n"
            "  return [{\n"
            "    json: {\n"
            "      ...config,\n"
            "      scenes: normScenes,\n"
            "      openRouterRequest: {\n"
            "        model:    config.orModel || 'mistralai/mistral-large',\n"
            "        messages: [{ role: 'user', content: 'dummy' }],\n"
            "        temperature: 0.1,\n"
            "        max_tokens:  10\n"
            "      }\n"
            "    }\n"
            "  }];\n"
            "}\n\n"
            "let scenes = [];\n"
            "if (config.isPreformatted) {\n"
            "  scenes = config.preformattedScenes;\n"
            "} else {\n"
            "  const rawText =\n"
            "    resp.message?.content || resp.response ||\n"
            "    (() => { throw new Error('Coder bad response: ' + JSON.stringify(resp).substring(0, 200)); })();\n\n"
            "  const cleaned = rawText.replace(/```json\\n?/gi,'').replace(/```\\n?/g,'').trim();\n\n"
            "  try {\n"
            "    const p = JSON.parse(cleaned);\n"
            "    scenes   = p.scenes || Object.values(p).find(v => Array.isArray(v)) || [];\n"
            "  } catch {\n"
            "    const m = cleaned.match(/\\{[\\s\\S]*\\}/);\n"
            "    if (!m) throw new Error('No JSON in coder output: ' + cleaned.substring(0, 300));\n"
            "    try {\n"
            "      const p = JSON.parse(m[0]);\n"
            "      scenes  = p.scenes || Object.values(p).find(v => Array.isArray(v)) || [];\n"
            "    } catch { throw new Error('Invalid JSON from coder.'); }\n"
            "  }\n"
            "}\n\n"
            "if (!scenes.length) throw new Error('No scenes found to parse.');\n\n"
            "const normScenes = scenes.map((s, i) => ({\n"
            "  n:          s.n || s.scene_number || (i + 1),\n"
            "  title:      s.title      || `Scene ${i + 1}`,\n"
            "  story_text: s.story_text || s.scene_text || '',\n"
            "  dialogue:   s.dialogue !== undefined ? s.dialogue : null,\n"
            "  setting:    s.setting    || 'unknown',\n"
            "  emotion:    s.emotion    || s.primary_emotion || 'dramatic',\n"
            "  action:     s.action     || s.action_beat || '',\n"
            "  mood_tags:  Array.isArray(s.mood_tags) ? s.mood_tags : ['cinematic'],\n"
            "  colors:     Array.isArray(s.colors) ? s.colors :\n"
            "              Array.isArray(s.color_palette) ? s.color_palette : ['dark blue','gold','shadow'],\n"
            "  image_prompt: s.image_prompt || null,\n"
            "  negative_prompt: s.negative_prompt || null,\n"
            "  video_prompt: s.video_prompt || null\n"
            "}));\n\n"
            "const orSystem =\n"
            "  `You are a senior manhwa script editor. Polish scene descriptions and dialogue.\\n` +\n"
            "  `Return the SAME JSON structure — only improve story_text and dialogue.\\n\\n` +\n"
            "  `IMPROVE:\\n` +\n"
            "  `• story_text → cinematic show-don't-tell, max 15-40 words total (1-2 punchy sentences). Must be very short for a 2-15 second video clip.\\n` +\n"
            "  `• dialogue → natural, subtext-rich, character-revealing. null if no dialogue fits.\\n\\n` +\n"
            "  `DO NOT CHANGE: n, title, setting, emotion, action, mood_tags, colors\\n` +\n"
            "  `Character voice: ${config.charDesc}\\n` +\n"
            "  `Genre: ${config.genre}\\n\\n` +\n"
            "  `Return ONLY JSON: {\"scenes\":[...]}`;\n\n"
            "return [{\n"
            "  json: {\n"
            "    ...config,\n"
            "    scenes: normScenes,\n"
            "    openRouterRequest: {\n"
            "      contents: [{\n"
            "        role: 'user',\n"
            "        parts: [{ text: `${orSystem}\\n\\nPolish story_text and dialogue:\\n\\n${JSON.stringify({scenes: normScenes}, null, 2)}` }]\n"
            "      }],\n"
            "      generationConfig: {\n"
            "        temperature: 0.75,\n"
            "        maxOutputTokens: Math.min(normScenes.length * 400, 32000),\n"
            "        responseMimeType: 'application/json'\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}];"
        )

    # --- Parse OpenRouter -> Build Gemini: add isComplete bypass and fix truncation map ---
    if node['name'] == '\U0001f5bc\ufe0f Parse OpenRouter \u2192 Build Gemini':
        visual_escaped = ADDICTIVE_VISUAL_INSTRUCTION.replace('\\', '\\\\').replace('`', '\\`').replace("'", "\\'").replace('\n', '\\n')
        
        node['parameters']['jsCode'] = (
            "const resp   = $input.first().json;\n"
            "const config = $('📋 Parse Coder → Build OpenRouter').first().json;\n\n"
            "if (config.isComplete || config.isPreformatted) {\n"
            "  return [{\n"
            "    json: {\n"
            "      ...config,\n"
            "      polishedScenes: config.scenes,\n"
            "      geminiRequest: {\n"
            "        contents: [{\n"
            "          role: 'user',\n"
            "          parts: [{ text: 'dummy' }]\n"
            "        }]\n"
            "      }\n"
            "    }\n"
            "  }];\n"
            "}\n\n"
            "// Merge Gemini dialogue polish (fallback to Stage 3 scenes if it fails)\n"
            "let polishedScenes = config.scenes;\n\n"
            "// Try Gemini response format first, then OpenRouter format as fallback\n"
            "const geminiText = resp.candidates?.[0]?.content?.parts?.[0]?.text || '';\n"
            "const orText = resp.choices?.[0]?.message?.content || '';\n"
            "const responseText = geminiText || orText;\n\n"
            "if (responseText) {\n"
            "  try {\n"
            "    const raw = responseText\n"
            "      .replace(/```json\\n?/gi,'').replace(/```\\n?/g,'').trim();\n"
            "    const p   = JSON.parse(raw);\n"
            "    const arr = p.scenes || Object.values(p).find(v => Array.isArray(v));\n"
            "    if (Array.isArray(arr) && arr.length) {\n"
            "      polishedScenes = config.scenes.map((scene, i) => {\n"
            "        const polished = arr.find(s => (s.n === scene.n || s.scene_number === scene.n)) || arr[i];\n"
            "        if (polished) {\n"
            "          return {\n"
            "            ...scene,\n"
            "            story_text: polished.story_text || scene.story_text,\n"
            "            dialogue:   polished.dialogue !== undefined ? polished.dialogue : scene.dialogue\n"
            "          };\n"
            "        }\n"
            "        return scene;\n"
            "      });\n"
            "    }\n"
            "  } catch { /* silent fallback */ }\n"
            "}\n\n"
            "// GEMINI AI STUDIO job: expert ComfyUI / AnythingXL prompt engineering\n"
            "const geminiSystem =\n"
            f"  `{visual_escaped}\\n\\n` +\n"
            "  `You are an expert AI image prompt engineer for AnythingXL (Stable Diffusion XL).\\n` +\n"
            "  `Write optimized prompts for manhwa/webtoon style images.\\n\\n` +\n"
            "  `For each scene output:\\n` +\n"
            "  `image_prompt — include ALL of these:\\n` +\n"
            "  `  • Quality tags: masterpiece, best quality, highly detailed, 8k\\n` +\n"
            "  `  • Character (ALWAYS): ${config.charDesc}\\n` +\n"
            "  `  • Art style: ${config.artStyle}\\n` +\n"
            "  `  • Specific camera angle (low angle / dutch tilt / overhead / close-up / etc)\\n` +\n"
            "  `  • Lighting setup (golden hour / harsh side light / rim light / neon glow / etc)\\n` +\n"
            "  `  • Color grading (warm tones / desaturated / high contrast / etc)\\n` +\n"
            "  `  • Narrative Literal: Explicitly describe EXACTLY what is happening in the scene based on the story text (who is doing what, specific actions, what objects are they interacting with). Do NOT just describe the mood.\\n\\n` +\n"
            "  `video_prompt — 3 second motion description:\\n` +\n"
            "  `  • Camera: slow dolly push / tracking shot / slow zoom out / etc\\n` +\n"
            "  `  • Character action: specific movement\\n` +\n"
            "  `  • Environment: wind in hair / rain falling / dust particles / etc\\n\\n` +\n"
            "  `negative_prompt — always:\\n` +\n"
            "  `worst quality, low quality, blurry, bad anatomy, deformed, ugly, watermark, text\\n\\n` +\n"
            "  `Output ONLY JSON: {\\\"prompts\\\":[{\\\"n\\\":1,\\\"image_prompt\\\":\\\"...\\\",\\\"negative_prompt\\\":\\\"...\\\",\\\"video_prompt\\\":\\\"...\\\"}]}`;\n\n"
            "const sceneSummary = polishedScenes.map(s =>\n"
            "  `Scene ${s.n} — ${s.title}\\nText: ${s.story_text}\\nSetting: ${s.setting}\\nEmotion: ${s.emotion}\\nColors: ${s.colors.join(', ')}\\nMood: ${s.mood_tags.join(', ')}`\n"
            ").join('\\n\\n');\n\n"
            "return [{\n"
            "  json: {\n"
            "    ...config,\n"
            "    polishedScenes,\n"
            "    geminiRequest: {\n"
            "      contents: [{\n"
            "        role: 'user',\n"
            "        parts: [{ text: `Write AnythingXL image prompts for each scene. Output only JSON.\\n\\n${sceneSummary}` }]\n"
            "      }],\n"
            "      systemInstruction: { parts: [{ text: geminiSystem }] },\n"
            "      generationConfig: {\n"
            "        temperature: 0.6,\n"
            "        maxOutputTokens: Math.min(polishedScenes.length * 800, 32000),\n"
            "        responseMimeType: 'application/json'\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}];"
        )

    # --- Assemble Final Payload ---
    if node['name'] == '🧩 Assemble Final Payload':
        node['parameters']['jsCode'] = (
            "const resp   = $input.first().json;\n"
            "const config = $('🖼️ Parse OpenRouter → Build Gemini').first().json;\n\n"
            "if (config.isComplete || config.isPreformatted) {\n"
            "  const finalScenes = config.polishedScenes.map((scene, i) => {\n"
            "    const original = (config.preformattedScenes && config.preformattedScenes[i]) || {};\n"
            "    return {\n"
            "      scene_number:  scene.n,\n"
            "      scene_title:   scene.title,\n"
            "      story_text:    scene.story_text,\n"
            "      dialogue:      scene.dialogue || null,\n"
            "      setting:       scene.setting,\n"
            "      emotion:       scene.emotion,\n"
            "      action:        scene.action,\n"
            "      mood_tags:     scene.mood_tags,\n"
            "      color_palette: scene.colors,\n"
            "      image_prompt:  scene.image_prompt || original.image_prompt || '',\n"
            "      negative_prompt: scene.negative_prompt || original.negative_prompt || '',\n"
            "      video_prompt:  scene.video_prompt || original.video_prompt || '',\n"
            "      width:  original.width || 1344,\n"
            "      height: original.height || 768,\n"
            "      steps:  original.steps || 30,\n"
            "      cfg:    original.cfg || 7.5,\n"
            "      seed:   original.seed || config.seed\n"
            "    };\n"
            "  });\n\n"
            "  return [{\n"
            "    json: {\n"
            "      project_name:     config.projectName,\n"
            "      title:            config.projectName,\n"
            "      genre:            config.genre,\n"
            "      art_style:        config.artStyle,\n"
            "      char_desc:        config.charDesc,\n"
            "      consistency_seed: config.seed,\n"
            "      total_scenes:     finalScenes.length,\n"
            "      models_used: {\n"
            "        scene_breakdown: 'skipped (preformatted)',\n"
            "        creative_expand: 'skipped (preformatted)',\n"
            "        json_structure:  'skipped (preformatted)',\n"
            "        dialogue_polish: 'skipped (preformatted)',\n"
            "        image_prompts:   config.isComplete ? 'skipped (preformatted)' : 'skipped (preformatted — prompts needed)'\n"
            "      },\n"
            "      scenes: finalScenes,\n"
            "      pipeline_options: {\n"
            "        generate_images:    true,\n"
            "        generate_video:     true,\n"
            "        generate_tts:       true,\n"
            "        use_ken_burns:      true,\n"
            "        output_format:      'mp4',\n"
            "        fps:                24,\n"
            "        scene_duration_sec: 5\n"
            "      }\n"
            "    }\n"
            "  }];\n"
            "}\n\n"
            "// Parse Gemini (AI Studio format)\n"
            "let geminiPrompts = [];\n"
            "try {\n"
            "  const text    = resp.candidates?.[0]?.content?.parts?.[0]?.text || '';\n"
            "  const cleaned = text.replace(/```json\\n?/gi,'').replace(/```\\n?/g,'').trim();\n"
            "  geminiPrompts = JSON.parse(cleaned).prompts || [];\n"
            "} catch { /* fallback to generated prompts below */ }\n\n"
            "// Merge all 5 stages into the final scene objects\n"
            "const finalScenes = config.polishedScenes.map((scene, i) => {\n"
            "  const gd = geminiPrompts.find(p => p.n === scene.n) || geminiPrompts[i] || {};\n"
            "  const original = (config.preformattedScenes && config.preformattedScenes[i]) || {};\n\n"
            "  return {\n"
            "    scene_number:  scene.n,\n"
            "    scene_title:   scene.title,\n"
            "    story_text:    scene.story_text,\n"
            "    dialogue:      scene.dialogue || null,\n"
            "    setting:       scene.setting,\n"
            "    emotion:       scene.emotion,\n"
            "    action:        scene.action,\n"
            "    mood_tags:     scene.mood_tags,\n"
            "    color_palette: scene.colors,\n"
            "    // Image gen — Gemini prompt or fallback\n"
            "    image_prompt: gd.image_prompt ||\n"
            "      `masterpiece, best quality, highly detailed, 8k, ${config.artStyle}, ${config.charDesc}, ${scene.setting}, ${scene.emotion} mood, cinematic lighting`,\n"
            "    negative_prompt: gd.negative_prompt ||\n"
            "      'worst quality, low quality, blurry, bad anatomy, deformed, ugly, watermark, text, cropped',\n"
            "    video_prompt: gd.video_prompt ||\n"
            "      `Slow cinematic push. ${config.charDesc}. ${scene.emotion}. ${config.artStyle}. 3 seconds.`,\n"
            "    // ComfyUI params — prefer original preformatted values\n"
            "    width:  original.width || 1344,\n"
            "    height: original.height || 768,\n"
            "    steps:  original.steps || 30,\n"
            "    cfg:    original.cfg || 7.5,\n"
            "    seed:   original.seed || config.seed\n"
            "  };\n"
            "});\n\n"
            "return [{\n"
            "  json: {\n"
            "    project_name:     config.projectName,\n"
            "    title:            config.projectName,\n"
            "    genre:            config.genre,\n"
            "    art_style:        config.artStyle,\n"
            "    char_desc:        config.charDesc,\n"
            "    consistency_seed: config.seed,\n"
            "    total_scenes:     finalScenes.length,\n"
            "    models_used: {\n"
            "      scene_breakdown: 'gemini — gemini-2.5-flash',\n"
            "      creative_expand: 'ollama — huihui_ai/qwen2.5-abliterate:7b',\n"
            "      json_structure:  'ollama — Qwen2.5-Coder-7B-Uncensored',\n"
            "      dialogue_polish: `openrouter — ${config.orModel}`,\n"
            "      image_prompts:   'google — gemini-2.5-flash'\n"
            "    },\n"
            "    scenes: finalScenes,\n"
            "    pipeline_options: {\n"
            "      generate_images:    true,\n"
            "      generate_video:     true,\n"
            "      generate_tts:       true,\n"
            "      use_ken_burns:      true,\n"
            "      output_format:      'mp4',\n"
            "      fps:                24,\n"
            "      scene_duration_sec: 5\n"
            "    }\n"
            "  }\n"
            "}];"
        )

    # --- Update sticky notes ---
    if node['type'] == 'n8n-nodes-base.stickyNote':
        content = node['parameters'].get('content', '')
        if "GROQ" in content:
            content = content.replace("GROQ", "xAI (Grok)")
            content = content.replace("llama-3.3-70b-versatile", "grok-beta")
            content = content.replace("Groq", "xAI")
            node['parameters']['content'] = content


# =============================================
# FIX CONNECTIONS
# =============================================
name_fixes = {
    "\u2460 xAI Grok \u2014 Scene Breakdown": "\u2460 Gemini \u2014 Scene Breakdown",
    "\u2460 Groq \u2014 Scene Breakdown": "\u2460 Gemini \u2014 Scene Breakdown"
}

new_connections = {}
for src, data in flow['connections'].items():
    fixed_src = name_fixes.get(src, src)
    fixed_data = {}
    for conn_type, outputs in data.items():
        fixed_outputs = []
        for output_list in outputs:
            fixed_list = []
            for target in output_list:
                fixed_target = dict(target)
                fixed_target['node'] = name_fixes.get(target['node'], target['node'])
                fixed_list.append(fixed_target)
            fixed_outputs.append(fixed_list)
        fixed_data[conn_type] = fixed_outputs
    new_connections[fixed_src] = fixed_data

flow['connections'] = new_connections

# =============================================
# SAVE
# =============================================
with open('n8n/auto_local_v3_configured.json', 'w', encoding='utf-8') as f:
    json.dump(flow, f, indent=2, ensure_ascii=False)

print("[OK] auto_local_v3_configured.json rebuilt from scratch!")
print()
print("Changes:")
print("  [FIX] formTrigger typeVersion 2.2 -> 2.1 (import error fix)")
print("  [FIX] All 7 previous bug fixes applied")
print("  [NEW] 100% FREE pipeline (no OpenRouter)")
print("  [NEW] Addictive story system instruction injected into Abliterate")
print("  [NEW] Addictive visual direction injected into Gemini")
print("  [NEW] API keys embedded, form fields optional")
