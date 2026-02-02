## Update 1.1 - Stability & Lifecycle Overhaul

**Release Date:** January 29, 2026

This update focuses on resolving hardware driver incompatibilities and ensuring clean process termination. It transitions the engine from high-level automation to low-level manual management for Audio and Windows API interfacing.

### 🔧 Critical Fixes
* **Fixed "Ghost Music" Bug:** Implemented a `WM_DESTROY` hook and a global `ACTIVE_SOUNDS` registry. The engine now intercepts the window close event and force-kills all active MCI audio threads before the process terminates.
* **Fixed Audio Driver Error:** Resolved the *"Driver cannot recognize parameter"* crash by removing the hardware-dependent `repeat` flag. Looping is now handled via a **Software Monitor** that polls playback status 60 times/second and restarts tracks manually.
* **Fixed File Permission Locks:** Added **Dynamic Session IDs** (SIDs) to all generated audio assets. Each run now creates unique filenames (e.g., `bounce_8271.wav`), preventing `PermissionError` clashes when restarting the engine rapidly.

### ⚙️ Core Improvements
* **Robust Melody Parser:** The music compiler now includes a sanitizer that strips parentheses and whitespace from input strings, preventing `ValueError` during float conversion.
* **Kernel Interface:** Switched to a manually defined `WNDCLASS` structure and verified `kernel32` linkage, improving compatibility across different Windows versions.
* **Physics Upgrade:** Collision resolution now utilizes **Minimum Translation Distance (MTD)** to prevent rigid bodies from sticking together during overlap.

============================================================================================
## Update 1.1m - Extended manual

**Release Date:** February 2, 2026

In this update, list of functions was added into a manual
