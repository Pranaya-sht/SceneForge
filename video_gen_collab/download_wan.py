import os
import requests
import time
from tqdm import tqdm

# All files needed for Wan2.1 T2V 1.3B in ComfyUI
# Total download: ~8.5 GB
files = [
    {
        "url": "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors",
        "dest": r"C:\Users\prana\Documents\ComfyUI\models\diffusion_models\wan2.1_t2v_1.3B_fp16.safetensors",
        "size_hint": "~3 GB"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "dest": r"C:\Users\prana\Documents\ComfyUI\models\text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "size_hint": "~5 GB"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
        "dest": r"C:\Users\prana\Documents\ComfyUI\models\vae\wan_2.1_vae.safetensors",
        "size_hint": "~400 MB"
    },
]

def download_with_resume(url, dest_path, size_hint):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    filename = os.path.basename(dest_path)

    while True:
        try:
            file_size = 0
            if os.path.exists(dest_path):
                file_size = os.path.getsize(dest_path)

            headers = {}
            if file_size > 0:
                headers['Range'] = f'bytes={file_size}-'

            print(f"\n{'='*60}")
            print(f"Downloading: {filename} ({size_hint})")
            print(f"Destination: {dest_path}")
            if file_size > 0:
                print(f"Resuming from: {file_size / (1024**3):.2f} GB")
            print(f"{'='*60}")

            response = requests.get(url, headers=headers, stream=True, timeout=60)

            if response.status_code == 416:
                print(f"[DONE] {filename} already fully downloaded! Skipping.")
                break

            if response.status_code == 200:
                file_size = 0
                mode = 'wb'
            elif response.status_code == 206:
                mode = 'ab'
            else:
                print(f"[ERROR] Error {response.status_code}. Retrying in 10 seconds...")
                time.sleep(10)
                continue

            total_size = int(response.headers.get('content-length', 0)) + file_size

            with open(dest_path, mode) as f:
                with tqdm(
                    initial=file_size,
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=filename
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):  # 8MB chunks
                        if chunk:
                            f.write(chunk)
                            f.flush()
                            pbar.update(len(chunk))

            print(f"\n[DONE] {filename} downloaded successfully!")
            break

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            print(f"[WARN] Connection dropped: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
        except KeyboardInterrupt:
            print(f"\n\n[PAUSED] Download paused. Run again to resume from where you left off.")
            exit(0)
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}. Retrying in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    print("\n[START] Wan2.1 T2V 1.3B ComfyUI Model Downloader")
    print("=" * 60)
    print("Files to download:")
    for f in files:
        print(f"  • {os.path.basename(f['dest'])} ({f['size_hint']})")
    print("=" * 60)
    print("[INFO] Downloads are resumable - safe to Ctrl+C and restart!\n")

    for file_info in files:
        download_with_resume(file_info["url"], file_info["dest"], file_info["size_hint"])

    print("\n" + "=" * 60)
    print("\n[COMPLETE] All Wan2.1 model files downloaded!")
    print("\nNext steps:")
    print("1. Restart ComfyUI Desktop")
    print("2. Go to Workflows → Workflow Templates")
    print("3. Search for 'Wan' and load the T2V 1.3B template")
    print("=" * 60)
