import os
import sys
import time
import requests

# Bulletproof downloader designed specifically to handle extreme connection drops
# without corrupting the Safetensors file.

url = "https://civitai.com/api/download/models/90854?type=Model&format=SafeTensor&size=pruned&fp=fp16"
dest = r"C:\Users\prana\Documents\ComfyUI\models\checkpoints\anything-v5.safetensors"

print("Starting Bulletproof Download for AnythingV5 (~2GB)...")

while True:
    headers = {}
    file_size = 0
    
    if os.path.exists(dest):
        file_size = os.path.getsize(dest)
        if file_size >= 2.10 * 1024 * 1024 * 1024: # ~2.1 GB
            headers['Range'] = f'bytes={file_size}-'
        elif file_size > 0:
            headers['Range'] = f'bytes={file_size}-'
        print(f"Resuming from: {file_size / (1024*1024*1024):.2f} GB")
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        
        if response.status_code == 416:
            print("Download finished!")
            break
            
        # CRITICAL FIX: If we ask for a Range and the server sends the WHOLE file (200),
        # appending it will corrupt the file! We must drop it and retry.
        if response.status_code == 200 and file_size > 0:
            print("WARNING: Server ignored resume request. Dropping to prevent corruption!")
            time.sleep(5)
            continue
            
        mode = 'ab' if file_size > 0 else 'wb'
        
        with open(dest, mode) as f:
            for chunk in response.iter_content(chunk_size=8192 * 10):
                if chunk:
                    f.write(chunk)
                    f.flush()
        
        print("\nSUCCESS! Download fully complete.")
        break
        
    except Exception as e:
        print(f"Connection dropped ({type(e).__name__}). Retrying in 5 seconds...")
        time.sleep(5)
