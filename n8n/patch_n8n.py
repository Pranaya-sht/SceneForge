import json

with open('auto.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Update connections
conn = data.get('connections', {})

# 1. Bypass 'Create Project Folder'
if '📖 Parse Groq Response' in conn:
    conn['📖 Parse Groq Response'] = {
        'main': [[{'node': '✂️ Split Scenes (Sequential Names)', 'type': 'main', 'index': 0}]]
    }
if '📁 Create Project Folder' in conn:
    del conn['📁 Create Project Folder']

# 2. Replace 'Upload to Google Drive' with 'Save File Locally'
if '🔗 Merge Video + Image Paths' in conn:
    conn['🔗 Merge Video + Image Paths']['main'][0][0]['node'] = '💾 Save File Locally'

conn['💾 Save File Locally'] = {
    'main': [[{'node': '🔄 One Scene At A Time', 'type': 'main', 'index': 0}]]
}
if '📤 Upload to Google Drive (Sequential)' in conn:
    del conn['📤 Upload to Google Drive (Sequential)']

data['connections'] = conn

# Update Nodes
new_nodes = []
for n in data['nodes']:
    name = n.get('name', '')
    
    # Drop Google Drive nodes
    if name == '📁 Create Project Folder' or name == '📤 Upload to Google Drive (Sequential)':
        continue
        
    # Update 'Split Scenes' code
    if name == '✂️ Split Scenes (Sequential Names)':
        n['parameters']['jsCode'] = """const storyData = $('📖 Parse Groq Response').first().json;

if (!storyData.scenes || storyData.scenes.length === 0) {
  throw new Error('No scenes to process.');
}

// Format a safe folder name
const safeProjectName = storyData.projectName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
const folderPath = `/output/${safeProjectName}`;

// Return one item per scene
return storyData.scenes.map(scene => ({
  json: {
    scene_number: scene.scene_number,
    scene_text: scene.scene_text,
    image_prompt: scene.image_prompt,
    video_prompt: scene.video_prompt,
    // Sequential filename
    file_prefix: String(scene.scene_number).padStart(3, '0') + '_scene',
    folderPath: folderPath,
    consistencySeed: storyData.consistencySeed,
    totalScenes: storyData.totalScenes,
    projectName: storyData.projectName
  }
}));"""
        
    # Update Video Tag
    if name == '🏷️ Tag as Video (.mp4)':
        n['parameters']['jsCode'] = """const input = $input.first().json;
return [{
  json: {
    ...input,
    file_extension: '.mp4'
  },
  binary: $input.first().binary
}];"""
        
    # Update Image Tag
    if name == '🏷️ Tag as Image (.jpg)':
        n['parameters']['jsCode'] = """const input = $input.first().json;
return [{
  json: {
    ...input,
    file_extension: '.jpg'
  },
  binary: $input.first().binary
}];"""

    new_nodes.append(n)

# Add 'Write Binary File' node
new_nodes.append({
    'parameters': {
        'fileName': '={{ $json.folderPath }}/{{ $json.file_prefix }}{{ $json.file_extension }}',
        'options': {
            'append': False,
            'createDirectory': True
        }
    },
    'type': 'n8n-nodes-base.writeBinaryFile',
    'typeVersion': 1,
    'position': [2360, 140],
    'id': 'node-save-locally',
    'name': '💾 Save File Locally'
})

data['nodes'] = new_nodes

with open('auto_local.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)
print('Saved auto_local.json successfully.')
