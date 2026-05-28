"""
Download Animagine XL 3.1 for local ComfyUI.
Uses aria2c or PowerShell for reliable, resumable download.
Run once: python download_model.py
"""
import os
import sys
import subprocess
import shutil

MODEL_URL = "https://huggingface.co/cagliostrolab/animagine-xl-3.1/resolve/main/animagine-xl-3.1.safetensors"
MODEL_NAME = "animagine-xl-3.1.safetensors"
COMFYUI_CKPT_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "ComfyUI", "resources", "ComfyUI", "models", "checkpoints"
)

def main():
    if not os.path.isdir(COMFYUI_CKPT_DIR):
        print(f"ERROR: ComfyUI checkpoints dir not found: {COMFYUI_CKPT_DIR}")
        sys.exit(1)

    dest = os.path.join(COMFYUI_CKPT_DIR, MODEL_NAME)

    # Clean up partial downloads
    tmp = dest + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
        print(f"Removed partial download: {tmp}")

    if os.path.exists(dest) and os.path.getsize(dest) > 5e9:
        size_gb = os.path.getsize(dest) / 1e9
        print(f"Model already exists: {dest} ({size_gb:.2f} GB)")
        return

    print(f"Downloading {MODEL_NAME} (~6.5 GB)...")
    print(f"To: {COMFYUI_CKPT_DIR}")
    print()

    # Use PowerShell's BITS transfer (built into Windows, supports resume)
    ps_cmd = (
        f'Start-BitsTransfer -Source "{MODEL_URL}" '
        f'-Destination "{dest}" '
        f'-DisplayName "Downloading Animagine XL 3.1" '
        f'-Description "6.5 GB model for ComfyUI"'
    )

    try:
        print("Using Windows BITS Transfer (resume-capable)...")
        subprocess.run(
            ["powershell", "-Command", ps_cmd],
            check=True
        )
    except subprocess.CalledProcessError:
        # Fallback: try curl (ships with Windows 10+)
        print("BITS failed. Trying curl...")
        try:
            subprocess.run(
                ["curl", "-L", "-C", "-", "-o", dest, MODEL_URL],
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("\nAll download methods failed.")
            print("Please download manually:")
            print(f"  URL:  {MODEL_URL}")
            print(f"  Save: {dest}")
            sys.exit(1)

    if os.path.exists(dest) and os.path.getsize(dest) > 5e9:
        size_gb = os.path.getsize(dest) / 1e9
        print(f"\nDone! Model saved: {dest} ({size_gb:.2f} GB)")
    else:
        print("\nDownload may be incomplete. Please try again.")
        sys.exit(1)

if __name__ == "__main__":
    main()
