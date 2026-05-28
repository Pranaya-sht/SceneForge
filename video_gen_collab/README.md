# Remote Colab & Distributed Google Drive Video Generation

This folder contains the scripts and notebooks required to run a distributed rendering system using **Google Drive** and remote GPU platforms (**Google Colab** and **Kaggle**). 

This setup allows you to leverage free, high-performance cloud GPUs (16GB VRAM) to render long-form videos (like 80-scene anime/manhwa recaps) without overloading your local PC.

---

## 🚀 Recommended Workflow: Wan2GP + LTX-2 (New & Premium)

We have upgraded the pipeline to support **Wan2GP** (a lightweight, highly optimized batch video generation server and CLI) supporting **Wan 2.1** and **LTX-2** models.

### Why Wan2GP?
1. **Lightweight & VRAM Efficient**: Generates beautiful videos on a single T4 GPU using the Wan 2.1 1.3B model (`--t2v-1-3B`).
2. **Auto-Downloads Models**: No more manual HuggingFace downloading scripts.
3. **Headless Batch Mode**: Stable command-line execution that integrates seamlessly with our lock-manager.
4. **Style & Character Consistency**: Pre-configured style prompts (Anime/Manhwa webtoon look) and character consistency prefixes.

### 📂 File Explanations

#### New Wan2GP Files (Recommended)
*   **`Wan2GP_Batch_Worker.ipynb`**: Simplified, robust Google Colab notebook. Runs the Wan2GP worker in 8 clean cells.
*   **`wan2gp_worker.py`**: The distributed video worker script. Connects to Wan2GP, claims scenes, runs text-to-video, and merges with TTS audio.

#### Legacy ComfyUI Files
*   **`Colab_Distributed_Worker.ipynb`**: Interactive Google Colab notebook using ComfyUI.
*   **`Kaggle_Distributed_Worker.ipynb`**: ComfyUI notebook configured for Kaggle.
*   **`drive_worker.py`**: The old worker script that interacts with ComfyUI API.

#### Distributed State & Loop Management
*   **`drive_state.py`**: The distributed "brain." Manages scene claiming using file-based lock and heartbeat detection (preventing multiple workers from rendering the same scene, and reclaiming scenes if a worker crashes).
*   **`drive_uploader.py`**: The local script used to prep the environment. It generates all narration audio files locally and uploads them along with the script to Google Drive.
*   **`orchestrator.py`**: Local command-line helper for configuring remote rendering options.

---

## 🛠️ Step-by-Step Distributed Setup Guide (Wan2GP)

### Step 1: Initialize Google Drive Structure (Local PC)
First, prepare your Google Drive with the master script and generated audio files. Run the local TTS server (`python tts_server.py`) and execute:
```bash
python drive_uploader.py --drive-path "G:\My Drive\AnimeFactory"
```
*Note: Replace with your actual mounted Google Drive path. This creates the folder structure, generates all narration MP3 files, and copies them to Drive.*

### Step 2: Open Google Colab
1. Upload **`Wan2GP_Batch_Worker.ipynb`** to [Google Colab](https://colab.research.google.com/).
2. Select **Runtime -> Change runtime type** and ensure you have selected a **GPU (T4, L4, or A100)**.
3. Run cells **1 → 7** in order. Cell 3 will automatically boot the Wan2GP server (downloading the model on the first run, which takes 5-10 minutes).
4. Run Cell 7 to start the worker. It will automatically claim pending scenes, generate videos matching the prompts, and merge them with the narration.

### Step 3: Monitor Progress and Stitch Final Video
You can monitor the progress by looking at `G:\My Drive\AnimeFactory\state\progress.json`.

Once all scenes are marked as `done`, run Cell 8 (**Final Stitch**) in your Colab notebook to merge the individual `.mp4` scene files into the final high-definition movie.

