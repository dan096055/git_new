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

============================================================================================

## Update 1.2 - High-Fidelity Audio & Stability

**Release Date:** January 30, 2026

This update fundamentally overhauls the audio engine, eliminating sound distortion and Windows driver incompatibilities. We have moved away from simple resampling methods in favor of mathematically precise interpolation.

### 🔊 Audio Engine (High-Fidelity)
* **The Problem:** Previously, changing the pitch of audio samples used "Nearest Neighbor" resampling. This resulted in duplicate bytes, causing harsh metallic "crunching" and digital artifacts (aliasing), especially on lower notes.
* **The Solution:** Implemented **Linear Interpolation (Lerp)**.
    * The engine now calculates the exact fractional values between audio samples using the formula: `val = y1 + (y2 - y1) * (x - x1)`.
    * This smooths out the waveform, resulting in clean, high-quality playback for imported files.

### 🛠 Stability Fixes
* **Fixed Driver Crash (MCI Error):** The *"The driver cannot recognize parameter"* error was caused by the `repeat` flag being incompatible with certain modern sound cards.
    * **Fix:** We replaced hardware looping with a **Software Monitor**. The engine now polls the playback status 60 times per second and manually restarts the track when it stops. This guarantees compatibility on all systems.
* **Fixed "Ghost Music":** Previously, music would continue playing in the background after the window was closed because the MCI thread was not terminated.
    * **Fix:** Added a `WM_DESTROY` event hook. When the window closes, the engine explicitly sends a `close` command to all active sound objects, instantly freeing system resources.

### ⚙️ Other Improvements
* **Full Structure Restored:** The source code has been unpacked to its full format (~370 lines) with detailed documentation and comments restored for better readability and maintenance.a
