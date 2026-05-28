import json
import os

with open('n8n/auto_local.json', 'r', encoding='utf-8') as f:
    flow = json.load(f)

# Find the essential nodes
nodes = flow['nodes']
connections = flow['connections']

keep_node_names = [
    "📖 Full Setup Guide",
    "Groq Note",
    "📝 Script Input Form",
    "🔧 Build Groq Request",
    "🧠 Groq API (Script → Prompts)",
    "📖 Parse Groq Response"
]

new_nodes = [n for n in nodes if n['name'] in keep_node_names]

# Add the HTTP Trigger node
http_node = {
    "parameters": {
        "method": "POST",
        "url": "http://host.docker.internal:5000/trigger",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $json }}",
        "options": {}
    },
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.3,
    "position": [ 700, 220 ],
    "id": "node-trigger-local-pipeline",
    "name": "🚀 Trigger Local Pipeline"
}
new_nodes.append(http_node)

# Add a sticky note explaining the new flow
sticky_node = {
    "parameters": {
        "content": "## 🚀 FULLY LOCAL PIPELINE\n\nWhen Groq finishes the script, n8n sends it to your local Python server (`pipeline_server.py`).\n\nThe Python server then:\n1. Auto-generates TTS voices\n2. Sends prompts to ComfyUI for 16:9 images\n3. Uses FFmpeg to apply Ken Burns motion\n4. Stitches the final YouTube video!\n\nAll files saved to `reels/output/`",
        "height": 250,
        "width": 380,
        "color": 2
    },
    "type": "n8n-nodes-base.stickyNote",
    "typeVersion": 1,
    "position": [ 680, -60 ],
    "id": "sticky-local-pipeline",
    "name": "Local Pipeline Note"
}
new_nodes.append(sticky_node)


# Rebuild connections
new_connections = {
    "📝 Script Input Form": {
        "main": [
            [{"node": "🔧 Build Groq Request", "type": "main", "index": 0}]
        ]
    },
    "🔧 Build Groq Request": {
        "main": [
            [{"node": "🧠 Groq API (Script → Prompts)", "type": "main", "index": 0}]
        ]
    },
    "🧠 Groq API (Script → Prompts)": {
        "main": [
            [{"node": "📖 Parse Groq Response", "type": "main", "index": 0}]
        ]
    },
    "📖 Parse Groq Response": {
        "main": [
            [{"node": "🚀 Trigger Local Pipeline", "type": "main", "index": 0}]
        ]
    }
}

flow['nodes'] = new_nodes
flow['connections'] = new_connections
flow['name'] = "🎬 16:9 Local YouTube Pipeline (n8n + Python)"

with open('n8n/auto_local_v2.json', 'w', encoding='utf-8') as f:
    json.dump(flow, f, indent=2)

print("Created n8n/auto_local_v2.json successfully.")
