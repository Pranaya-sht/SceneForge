"""
=============================================================
  DRIVE STATE MANAGER
  The distributed brain of the AI Video Factory.
=============================================================

This module handles ALL shared state through Google Drive.
It implements:
  - Scene claiming with file-based locks
  - Heartbeat system to detect crashed workers
  - Atomic writes (.tmp → .mp4) to prevent corruption
  - Progress tracking across multiple workers

Google Drive is used as both the database AND the file store.
Workers on Colab/Kaggle mount Drive directly and read/write files.
No network APIs needed — just filesystem operations.

Usage:
  state = DriveState("/content/drive/MyDrive/AnimeFactory")
  scene = state.claim_next_scene("worker_abc123")
  # ... generate video ...
  state.complete_scene(scene["id"], "/path/to/output.tmp")
"""

import json
import os
import shutil
import time
import threading
import uuid


class DriveState:
    """
    Manages distributed rendering state via Google Drive filesystem.
    
    Directory structure on Drive:
      AnimeFactory/
      ├── state/
      │   ├── master_script.json    ← Full story (read-only)
      │   ├── progress.json         ← Scene status tracking
      │   └── locks/                ← One .lock file per active scene
      ├── inputs/
      │   └── tts/                  ← Pre-generated audio files
      ├── outputs/
      │   └── scenes/              ← Completed scene videos
      └── logs/                    ← Per-worker log files
    """
    
    LOCK_STALE_SECONDS = 300  # 5 minutes = crashed worker
    HEARTBEAT_INTERVAL = 30   # Update lock every 30 seconds
    
    def __init__(self, drive_root):
        """
        Args:
            drive_root: Path to the AnimeFactory folder on mounted Drive.
                        e.g. "/content/drive/MyDrive/AnimeFactory"
        """
        self.root = drive_root
        self.state_dir = os.path.join(drive_root, "state")
        self.locks_dir = os.path.join(self.state_dir, "locks")
        self.inputs_dir = os.path.join(drive_root, "inputs")
        self.tts_dir = os.path.join(self.inputs_dir, "tts")
        self.outputs_dir = os.path.join(drive_root, "outputs")
        self.scenes_dir = os.path.join(self.outputs_dir, "scenes")
        self.logs_dir = os.path.join(drive_root, "logs")
        
        self.progress_file = os.path.join(self.state_dir, "progress.json")
        self.script_file = os.path.join(self.state_dir, "master_script.json")
        
        # Heartbeat thread reference (one per claimed scene)
        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()
    
    def ensure_dirs(self):
        """Create the full directory structure on Drive."""
        for d in [self.state_dir, self.locks_dir, self.inputs_dir,
                  self.tts_dir, self.outputs_dir, self.scenes_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)
    
    # ===========================================
    # PROGRESS FILE MANAGEMENT
    # ===========================================
    
    def load_progress(self):
        """Read progress.json from Drive. Returns dict."""
        if not os.path.exists(self.progress_file):
            return None
        with open(self.progress_file, "r") as f:
            return json.load(f)
    
    def save_progress(self, progress):
        """Write progress.json to Drive (atomic)."""
        progress["updated_at"] = time.time()
        tmp_path = self.progress_file + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(progress, f, indent=2)
        shutil.move(tmp_path, self.progress_file)
    
    def init_progress(self, scenes):
        """
        Initialize progress.json from a list of scenes.
        Called once by drive_uploader.py on your local PC.
        
        Args:
            scenes: List of scene dicts from master_script.json
        """
        progress = {
            "version": 1,
            "total_scenes": len(scenes),
            "scenes": {},
            "updated_at": time.time()
        }
        for i, scene in enumerate(scenes):
            scene_id = f"scene_{i+1:04d}"
            progress["scenes"][scene_id] = "pending"
        
        self.save_progress(progress)
        print(f"[STATE] Initialized {len(scenes)} scenes as 'pending'")
        return progress
    
    def load_script(self):
        """Read master_script.json from Drive."""
        with open(self.script_file, "r") as f:
            return json.load(f)
    
    # ===========================================
    # LOCK MANAGEMENT
    # ===========================================
    
    def _lock_path(self, scene_id):
        """Return the path to a scene's lock file."""
        return os.path.join(self.locks_dir, f"{scene_id}.lock")
    
    def _read_lock(self, scene_id):
        """Read a lock file. Returns dict or None if no lock exists."""
        path = self._lock_path(scene_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _write_lock(self, scene_id, worker_id):
        """Create or overwrite a lock file for a scene."""
        lock_data = {
            "worker_id": worker_id,
            "started_at": time.time(),
            "heartbeat": time.time()
        }
        path = self._lock_path(scene_id)
        with open(path, "w") as f:
            json.dump(lock_data, f)
        return lock_data
    
    def _update_heartbeat(self, scene_id):
        """Touch the lock file's heartbeat timestamp."""
        lock = self._read_lock(scene_id)
        if lock:
            lock["heartbeat"] = time.time()
            path = self._lock_path(scene_id)
            with open(path, "w") as f:
                json.dump(lock, f)
    
    def _is_lock_stale(self, scene_id):
        """
        Returns True if the lock is older than LOCK_STALE_SECONDS.
        A stale lock means the worker crashed and the scene should be reclaimed.
        """
        lock = self._read_lock(scene_id)
        if lock is None:
            return True  # No lock = available
        age = time.time() - lock.get("heartbeat", 0)
        return age > self.LOCK_STALE_SECONDS
    
    def _delete_lock(self, scene_id):
        """Remove a lock file."""
        path = self._lock_path(scene_id)
        if os.path.exists(path):
            os.remove(path)
    
    # ===========================================
    # HEARTBEAT THREAD
    # ===========================================
    
    def _start_heartbeat(self, scene_id):
        """Start a background thread that updates the lock every 30 seconds."""
        self._heartbeat_stop.clear()
        
        def _beat():
            while not self._heartbeat_stop.is_set():
                self._update_heartbeat(scene_id)
                self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL)
        
        self._heartbeat_thread = threading.Thread(target=_beat, daemon=True)
        self._heartbeat_thread.start()
    
    def _stop_heartbeat(self):
        """Stop the heartbeat thread."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None
    
    # ===========================================
    # SCENE CLAIMING + RELEASING
    # ===========================================
    
    def claim_next_scene(self, worker_id):
        """
        Find the next unclaimed scene and lock it for this worker.
        
        Returns:
            dict with scene info: {"id": "scene_0005", "index": 4, "data": {...}}
            or None if no scenes are available.
        """
        progress = self.load_progress()
        if not progress:
            print("[STATE] No progress.json found!")
            return None
        
        script = self.load_script()
        
        for scene_id, status in progress["scenes"].items():
            if status == "done":
                continue
            
            # Check if scene is locked by another worker
            if status == "locked":
                if not self._is_lock_stale(scene_id):
                    continue  # Another worker is actively processing this
                else:
                    # Stale lock — crashed worker. Steal it.
                    old_lock = self._read_lock(scene_id)
                    old_worker = old_lock.get("worker_id", "unknown") if old_lock else "unknown"
                    print(f"[STATE] Stealing stale lock on {scene_id} from crashed worker {old_worker}")
            
            # Claim this scene
            self._write_lock(scene_id, worker_id)
            progress["scenes"][scene_id] = "locked"
            self.save_progress(progress)
            
            # Start heartbeat
            self._start_heartbeat(scene_id)
            
            # Get scene data from script
            idx = int(scene_id.split("_")[1]) - 1
            scene_data = script[idx] if idx < len(script) else {}
            
            print(f"[STATE] Worker {worker_id} claimed {scene_id}")
            return {
                "id": scene_id,
                "index": idx,
                "data": scene_data
            }
        
        print("[STATE] No more scenes to process!")
        return None
    
    def complete_scene(self, scene_id, tmp_output_path):
        """
        Mark a scene as done after successful generation.
        
        1. Rename .tmp → .mp4 (atomic)
        2. Update progress.json
        3. Delete lock file
        4. Stop heartbeat
        """
        self._stop_heartbeat()
        
        # Atomic rename: .tmp → .mp4
        final_path = os.path.join(self.scenes_dir, f"{scene_id}.mp4")
        if os.path.exists(tmp_output_path):
            shutil.move(tmp_output_path, final_path)
            print(f"[STATE] Atomic write: {scene_id}.mp4 ({os.path.getsize(final_path) / 1024 / 1024:.1f} MB)")
        
        # Update progress
        progress = self.load_progress()
        progress["scenes"][scene_id] = "done"
        self.save_progress(progress)
        
        # Clean up lock
        self._delete_lock(scene_id)
        
        # Count progress
        done = sum(1 for s in progress["scenes"].values() if s == "done")
        total = progress["total_scenes"]
        print(f"[STATE] {scene_id} complete! Progress: {done}/{total} ({done/total*100:.1f}%)")
        
        return final_path
    
    def fail_scene(self, scene_id):
        """
        Release a scene back to 'pending' after a failure.
        Another worker can pick it up later.
        """
        self._stop_heartbeat()
        
        # Reset to pending
        progress = self.load_progress()
        progress["scenes"][scene_id] = "pending"
        self.save_progress(progress)
        
        # Clean up lock and any .tmp files
        self._delete_lock(scene_id)
        tmp_path = os.path.join(self.scenes_dir, f"{scene_id}.tmp")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        
        print(f"[STATE] {scene_id} released back to 'pending'")
    
    def cleanup_stale(self):
        """
        Clean up any leftover .tmp files and stale locks from crashed workers.
        Called at worker startup.
        """
        cleaned = 0
        
        # Clean .tmp files
        if os.path.exists(self.scenes_dir):
            for f in os.listdir(self.scenes_dir):
                if f.endswith(".tmp"):
                    os.remove(os.path.join(self.scenes_dir, f))
                    scene_id = f.replace(".tmp", "")
                    cleaned += 1
        
        # Clean stale locks and reset their scenes to pending
        progress = self.load_progress()
        if progress and os.path.exists(self.locks_dir):
            for f in os.listdir(self.locks_dir):
                if f.endswith(".lock"):
                    scene_id = f.replace(".lock", "")
                    if self._is_lock_stale(scene_id):
                        self._delete_lock(scene_id)
                        if scene_id in progress["scenes"]:
                            progress["scenes"][scene_id] = "pending"
                        cleaned += 1
            
            if cleaned > 0:
                self.save_progress(progress)
        
        if cleaned > 0:
            print(f"[STATE] Cleaned up {cleaned} stale items from crashed workers")
        else:
            print("[STATE] No stale items found. Clean start.")
    
    def get_summary(self):
        """Print a summary of the current pipeline status."""
        progress = self.load_progress()
        if not progress:
            print("[STATE] No progress file found.")
            return
        
        total = progress["total_scenes"]
        counts = {"done": 0, "pending": 0, "locked": 0}
        for status in progress["scenes"].values():
            counts[status] = counts.get(status, 0) + 1
        
        print(f"\n{'='*50}")
        print(f"  Pipeline Status")
        print(f"{'='*50}")
        print(f"  Total scenes:   {total}")
        print(f"  Done:           {counts['done']}")
        print(f"  Pending:        {counts['pending']}")
        print(f"  In Progress:    {counts['locked']}")
        print(f"  Progress:       {counts['done']/total*100:.1f}%")
        print(f"{'='*50}\n")
