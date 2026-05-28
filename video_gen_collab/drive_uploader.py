import os
import json
import requests
import argparse
import shutil
import time

# Configuration
TTS_SERVER_URL = "http://localhost:8765/tts"
SCRIPT_FILE = "master_script.json"
OUTPUT_DIR = "tts_output"

def generate_all_tts(scenes):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n[TTS] Generating audio for {len(scenes)} scenes...")
    
    success = 0
    failed = 0
    
    for scene in scenes:
        scene_id = scene.get("scene_id") or f"scene_{scenes.index(scene)+1:04d}"
        text = scene.get("narration") or scene.get("text")  # support both field names
        voice = scene.get("voice", "en-GB-RyanNeural")
        
        if not scene_id or not text:
            continue
            
        filename = f"{scene_id}.mp3"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        if os.path.exists(filepath):
            print(f"  [{scene_id}] Already exists: {filename}")
            success += 1
            continue
            
        try:
            resp = requests.post(TTS_SERVER_URL, json={
                "text": text,
                "voice": voice,
                "filename": filename
            }, timeout=30)
            
            if resp.status_code == 200:
                print(f"  [{scene_id}] Success: {filename}")
                success += 1
            else:
                print(f"  [{scene_id}] FAILED: {resp.text}")
                failed += 1
        except Exception as e:
            print(f"  [{scene_id}] Error connecting to TTS server: {e}")
            failed += 1
            
    print(f"\n[TTS] Complete: {success} success, {failed} failed")

def upload_to_drive_local(drive_path, script_file, scenes):
    """Simple copy to G: drive or mounted path"""
    state_dir = os.path.join(drive_path, "state")
    tts_dir = os.path.join(drive_path, "inputs", "tts")
    
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(tts_dir, exist_ok=True)
    os.makedirs(os.path.join(state_dir, "locks"), exist_ok=True)
    os.makedirs(os.path.join(drive_path, "outputs", "scenes"), exist_ok=True)

    # Copy script
    shutil.copy2(script_file, os.path.join(state_dir, "master_script.json"))
    print(f"[DRIVE] Synced {script_file} as master_script.json to {state_dir}")

    # Initialize progress.json if missing
    progress_file = os.path.join(state_dir, "progress.json")
    if not os.path.exists(progress_file):
        progress_data = {
            "project_name": "beast_contracts",
            "scenes": {scene.get("scene_id"): "pending" for scene in scenes}
        }
        with open(progress_file, "w", encoding="utf-8") as pf:
            json.dump(progress_data, pf, indent=2)
        print(f"[DRIVE] Initialized progress.json in {state_dir}")

    # Copy audio
    for scene in scenes:
        sid = scene.get("scene_id")
        src = os.path.join(OUTPUT_DIR, f"{sid}.mp3")
        dst = os.path.join(tts_dir, f"{sid}.mp3")
        if os.path.exists(src):
            shutil.copy2(src, dst)
    print(f"[DRIVE] Synced audio files to {tts_dir}")

def get_or_create_folder(drive_service, name, parent_id=None):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=q, fields="files(id,name)").execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    
    # Create the folder
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        metadata['parents'] = [parent_id]
    folder = drive_service.files().create(body=metadata, fields='id').execute()
    return folder.get('id')

def upload_or_update_file(drive_service, local_path, parent_id, filename=None):
    from googleapiclient.http import MediaFileUpload
    fname = filename or os.path.basename(local_path)
    
    # Check if file already exists in the parent folder
    q = f"name='{fname}' and '{parent_id}' in parents and trashed=false"
    existing = drive_service.files().list(q=q, fields="files(id)").execute().get('files', [])
    
    media = MediaFileUpload(local_path, resumable=True)
    if existing:
        file_id = existing[0]['id']
        print(f"  Updating {fname} on Google Drive...")
        drive_service.files().update(fileId=file_id, media_body=media).execute()
    else:
        print(f"  Uploading {fname} to Google Drive...")
        metadata = {'name': fname, 'parents': [parent_id]}
        drive_service.files().create(body=metadata, media_body=media).execute()

def upload_to_drive_api(sa_path, script_file, scenes):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    SCOPES = ['https://www.googleapis.com/auth/drive']
    try:
        creds = service_account.Credentials.from_service_account_info(
            json.load(open(sa_path, "r", encoding="utf-8")), scopes=SCOPES
        )
        drive_service = build('drive', 'v3', credentials=creds)
        print("[DRIVE API] Connected successfully via Service Account.")
        
        # 1. Get or create root AnimeFactory folder
        factory_id = get_or_create_folder(drive_service, "AnimeFactory")
        print(f"[DRIVE API] AnimeFactory folder ID: {factory_id}")
        
        # 2. Get or create state and inputs/tts folders
        state_id = get_or_create_folder(drive_service, "state", factory_id)
        get_or_create_folder(drive_service, "locks", state_id)
        
        inputs_id = get_or_create_folder(drive_service, "inputs", factory_id)
        tts_id = get_or_create_folder(drive_service, "tts", inputs_id)
        
        get_or_create_folder(drive_service, "outputs", factory_id)
        get_or_create_folder(drive_service, "scenes", get_or_create_folder(drive_service, "outputs", factory_id))
        
        # 3. Upload script
        print("[DRIVE API] Uploading/updating script...")
        upload_or_update_file(drive_service, script_file, state_id, "master_script.json")
        
        # 4. Initialize progress.json if missing on Drive
        q_prog = f"name='progress.json' and '{state_id}' in parents and trashed=false"
        existing_prog = drive_service.files().list(q=q_prog, fields="files(id)").execute().get('files', [])
        if not existing_prog:
            print("[DRIVE API] Creating progress.json...")
            temp_progress = "temp_progress.json"
            progress_data = {
                "project_name": "beast_contracts",
                "scenes": {scene.get("scene_id"): "pending" for scene in scenes}
            }
            with open(temp_progress, "w", encoding="utf-8") as pf:
                json.dump(progress_data, pf, indent=2)
            upload_or_update_file(drive_service, temp_progress, state_id, "progress.json")
            try:
                os.remove(temp_progress)
            except:
                pass
        
        # 5. Check existing audio files on Drive to avoid redundant uploads
        print("[DRIVE API] Checking existing audio files on Drive...")
        existing_files = {}
        page_token = None
        while True:
            results = drive_service.files().list(
                q=f"'{tts_id}' in parents and trashed=false",
                fields="nextPageToken, files(id,name)",
                pageToken=page_token
            ).execute()
            for f in results.get('files', []):
                existing_files[f['name']] = f['id']
            page_token = results.get('nextPageToken')
            if not page_token:
                break
            
        # 6. Upload audio
        print(f"[DRIVE API] Syncing audio files...")
        uploaded_count = 0
        skipped_count = 0
        for scene in scenes:
            sid = scene.get("scene_id")
            filename = f"{sid}.mp3"
            src = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(src):
                if filename in existing_files:
                    skipped_count += 1
                else:
                    upload_or_update_file(drive_service, src, tts_id, filename)
                    uploaded_count += 1
                    
        print(f"[DRIVE API] Audio sync complete: uploaded {uploaded_count}, skipped {skipped_count} existing.")
        print("\n✨ Google Drive API Sync Complete! Your Drive is ready for the Colab Worker.")
        return True
    except Exception as e:
        print(f"[ERROR] Google Drive API sync failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", default="master_script.json", help="Path to the JSON script file (default: master_script.json)")
    parser.add_argument("--drive-path", help="Path to Google Drive (e.g. G:\\My Drive\\AnimeFactory)")
    parser.add_argument("--skip-tts", action="store_true", help="Skip generating audio")
    parser.add_argument("--use-api", action="store_true", help="Force upload using service account Drive API")
    args = parser.parse_args()

    script_file = args.script

    if not os.path.exists(script_file):
        # Auto-fallback to parent directory if in video_gen_collab folder
        alt_path = os.path.join("..", script_file)
        if os.path.exists(alt_path):
            script_file = alt_path
            print(f"[INFO] Using script file found in parent directory: {script_file}")
        else:
            print(f"[ERROR] Script file not found: {script_file}")
            return

    with open(script_file, "r") as f:
        data = json.load(f)
        # Handle formats where scenes is under a top-level key or is the list directly
        if isinstance(data, list):
            scenes = data
        elif isinstance(data, dict) and "scenes" in data:
            scenes = data["scenes"]
        else:
            print("[ERROR] Could not find 'scenes' array in the script file.")
            return

    # 1. Generate TTS
    if not args.skip_tts:
        generate_all_tts(scenes)

    # 2. Sync to Drive
    sync_done = False
    
    # Try local copy if path specified and forced api is not set
    if args.drive_path and not args.use_api:
        drive_letter = os.path.splitdrive(args.drive_path)[0]
        if drive_letter and not os.path.exists(drive_letter):
            print(f"[WARNING] Drive letter '{drive_letter}' is not accessible.")
            
        if os.path.exists(os.path.dirname(args.drive_path)) or os.path.exists(args.drive_path):
            try:
                upload_to_drive_local(args.drive_path, script_file, scenes)
                print("\n✨ Local Sync Complete! Your Drive is ready for the Colab Worker.")
                sync_done = True
            except Exception as e:
                print(f"[WARNING] Local copy to drive path failed: {e}")
        else:
            print(f"[WARNING] Drive path '{args.drive_path}' is not accessible.")

    # Fallback to Google Drive API if local copy was not done or failed, or forced
    if not sync_done:
        sa_path = None
        candidates = [
            "service_account.json",
            "video_gen_collab/service_account.json",
            os.path.join(os.path.dirname(__file__), "service_account.json"),
            os.path.join(os.path.dirname(__file__), "..", "service_account.json")
        ]
        for c in candidates:
            if os.path.exists(c):
                sa_path = c
                break
        
        if sa_path:
            print(f"[INFO] Found service account credentials at '{sa_path}'. Syncing via Google Drive API...")
            sync_done = upload_to_drive_api(sa_path, script_file, scenes)
            
    if not sync_done:
        print("\n[INFO] No active sync path succeeded. Audio is generated in 'tts_output' folder.")
        print("       Please upload the contents of 'tts_output' to Drive manually.")

if __name__ == "__main__":
    main()


