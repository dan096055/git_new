#  WinMultimedia-Py Engine

A lightweight, **zero-dependency** multimedia engine for Windows, built entirely with Python and the native Windows API (`ctypes`).

##  The Mission
Most Python games rely on heavy libraries like `Pygame` or `Pyglet`. This engine takes a different path: it interfaces **directly** with the Windows OS kernels (`user32`, `gdi32`, `winmm`). It is designed for high performance, low overhead, and a deep understanding of how Windows handles graphics and sound.

---

##  Key Features

###  Graphics & UI
* **GDI Rendering:** Uses the Windows Graphics Device Interface for fast, flicker-free drawing.
* **Double Buffering:** Implements a memory Device Context (HDC) to eliminate screen tearing and flickering.
* **Dynamic Text:** Custom wrapper for `CreateFontW` and `TextOutW` for sharp, hardware-accelerated text.

###  Audio Engineering
* **Mathematical Synthesis:** Built-in oscillators for **Sine, Square, Triangle, and Sawtooth** waveforms.
* **Pitch-Shifting Sampler:** A custom resampling algorithm that allows you to load a single `.wav` file (e.g., a piano C3) and automatically maps it across the entire keyboard by mathematically adjusting playback speed.
* **Melody Interpreter:** Composers can write music using a simple string syntax: `"(Note_Octave_Duration)"`.

###  Input System
* **Real-time Input:** Uses `GetAsyncKeyState` for frame-perfect keyboard response, bypassing the standard (and slower) Python `input()` or event queues.

---

##  Musical Arrangement Example
The engine currently features a custom arrangement of **"Dark is the Night" (Тёмная ночь)**, demonstrating complex rhythmic structures like triplets and staccato "gates."

# The engine parses this into raw PCM frequencies and timings