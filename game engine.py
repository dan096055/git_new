"""
====================================================================================================
                                       ENGINE REFERENCE MANUAL (v1.2)
====================================================================================================
[1] KERNEL-LEVEL INTEGRATION
    This engine operates by mapping Python objects to C-structures defined in the Windows API. 
    It bypasses high-level wrappers to interact directly with core system libraries:
    - USER32.DLL: Manages the Window Procedure (WndProc), Message Pump, and Inputs.
    - GDI32.DLL: The Graphics Device Interface. Manages Device Contexts (HDC) and Raster Ops.
    - WINMM.DLL: The Windows Multimedia library for MCI (Multimedia Control Interface) commands.

[2] GRAPHICS & MEMORY MANAGEMENT
    - DOUBLE BUFFERING: To ensure 0% screen flickering, the engine allocates a 'Compatible Bitmap' 
      in system RAM. All drawing occurs on this back-buffer. The 'BitBlt' (Bit Block Transfer) 
      function then performs a high-speed memory-to-VRAM copy of the pixel data to the screen.
    - BITWISE COLORING: Colors are stored as 32-bit integers in 0x00BBGGRR format. 
      The RGB() function uses bit-shifting: (B << 16 | G << 8 | R) to pack channels.

[3] MATHEMATICAL PHYSICS (Elasticity & Vectors)
    - RADIUS OVERLAP: Collision is detected by comparing squared distance against the squared 
      sum of radii. This avoids the CPU-heavy square root calculation during the detection phase.
    - MTD RESOLUTION: If balls overlap, the engine calculates the Minimum Translation Distance 
      to physically separate them before calculating momentum.
    - MOMENTUM TRANSFER: Uses 2D Vector Projection (Dot Product) to swap scalar velocities 
      along the collision normal while preserving tangential velocity.

[4] AUDIO SYNTHESIS (High-Fidelity)
    - LINEAR INTERPOLATION (Lerp): When resampling audio (pitch shifting), the engine calculates
      the exact fractional value between two samples: val = y1 + (y2 - y1) * (x - x1).
      This eliminates the metallic "aliasing" noise found in simpler engines.
    - SOFTWARE LOOPING: v1.2 polls the hardware status 60 times/second. If a looping track stops,
      Python restarts it manually, bypassing unreliable hardware loop flags.

[5] PROCESS LIFECYCLE & CLEANUP
    - EXIT HOOKS: On WM_DESTROY, the engine iterates through the ACTIVE_SOUNDS registry and 
      explicitly sends 'close' commands to Windows. This prevents "ghost music" from 
      playing after the window is closed.
    - SESSION SAFETY: Unique Session IDs (SIDs) are appended to all .wav files to ensure 
      multiple runs do not result in PermissionErrors due to file locks.

[7] API REFERENCE
    --------------------------------------------------------------------------------------------
    CORE SYSTEM:
    * WindowEngine(title, width, height, bg_color) -> Main Game Instance.
      - .add(object) -> Registers an entity (Ball, Box, Sound) to the game loop.
      - .run()       -> Starts the infinite message pump.
    * RGB(r, g, b)   -> Returns a 32-bit integer color code (0x00BBGGRR).

    GRAPHICS:
    * Text.draw(hdc, x, y, text, color, size) -> Renders text to the buffer.
    * Box(x, y, w, h, color)    -> Creates a rectangle entity.
    * Circle(x, y, radius, color) -> Creates a circle entity.

    AUDIO & SYNTHESIS:
    * Sound(filename) -> Loads a WAV file into the MCI system.
      - .play(loop=False) -> Starts playback.
      - .update()         -> Must be called every frame to handle software looping.
    * Synth.tone(note, ms, vol, type) -> Generates raw PCM bytes for a specific note.
    * Synth.save(filename, data)      -> Writes PCM bytes to a valid WAV file.
    * Sampler(file, base_note) -> Imports WAV with Linear Interpolation.
    * Melody.compile(filename, bpm, notes_string) -> Generates a full song file.
      - Format: "(Note_Duration, ...)" e.g., "(C4_1/4, E4_1/4)"
      - Durations: 1/4 = Quarter note, 1/1 = Whole note.
    --------------------------------------------------------------------------------------------
====================================================================================================
"""

import ctypes
from ctypes import wintypes
import math
import struct
import random
import wave
import os
import time

# =================================================================================
# PART 1: WINDOWS API DEFINITIONS (The Core System)
# =================================================================================

# --- Load System DLLs ---
user32 = ctypes.windll.user32      # Window management, inputs
gdi32 = ctypes.windll.gdi32        # Graphics drawing functions
kernel32 = ctypes.windll.kernel32  # Memory and Module handling
winmm = ctypes.windll.winmm        # Audio and Multimedia

# --- Define Pointer Sizes ---
if ctypes.sizeof(ctypes.c_void_p) == 8: 
    LRESULT = ctypes.c_longlong # 64-bit
else: 
    LRESULT = ctypes.c_long     # 32-bit

# --- Define Missing Windows Types ---
if not hasattr(wintypes, 'HCURSOR'): wintypes.HCURSOR = wintypes.HANDLE
if not hasattr(wintypes, 'HBRUSH'): wintypes.HBRUSH = wintypes.HANDLE
if not hasattr(wintypes, 'LPCWSTR'): wintypes.LPCWSTR = ctypes.c_wchar_p

# --- Windows Constants ---
WS_OVERLAPPEDWINDOW = 0x00CF0000
CW_USEDEFAULT = 0x80000000
WM_DESTROY = 2
WM_PAINT = 0x000F
WM_TIMER = 0x0113
SW_SHOW = 5
SRCCOPY = 0x00CC0020
TRANSPARENT = 1

# Registry for cleanup
ACTIVE_SOUNDS = []

# --- C-Structures ---

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wintypes.HANDLE), ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

# Manually define WNDCLASS (Required for RegisterClassW)
WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
class WNDCLASS(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT),
                ('lpfnWndProc', WNDPROCTYPE),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE),
                ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HCURSOR),
                ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR),
                ('lpszClassName', wintypes.LPCWSTR)]

# --- Define Argument Types (Prevents Segmentation Faults) ---
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
gdi32.SetTextColor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
gdi32.SetBkMode.argtypes = [wintypes.HANDLE, ctypes.c_int]
gdi32.CreateFontW.argtypes = [ctypes.c_int]*5 + [wintypes.DWORD]*8 + [wintypes.LPCWSTR]
gdi32.TextOutW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
gdi32.GetTextExtentPoint32W.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)]
gdi32.Ellipse.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wintypes.HANDLE

def RGB(r, g, b): 
    """Converts R,G,B integers to a 32-bit color code."""
    return r | (g << 8) | (b << 16)

# =================================================================================
# PART 2: GRAPHICS & PHYSICS ENGINE
# =================================================================================

class Text:
    """Static Helper for Rendering Text."""
    @staticmethod
    def _font(hdc, size, color):
        gdi32.SetBkMode(hdc, TRANSPARENT)
        gdi32.SetTextColor(hdc, color)
        return gdi32.CreateFontW(size, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 0, "Arial")

    @staticmethod
    def draw(hdc, x, y, txt, col, sz=20):
        hF = Text._font(hdc, sz, col); oF = gdi32.SelectObject(hdc, hF)
        s = SIZE(); gdi32.GetTextExtentPoint32W(hdc, txt, len(txt), ctypes.byref(s))
        gdi32.TextOutW(hdc, int(x), int(y-s.cy), txt, len(txt))
        gdi32.SelectObject(hdc, oF); gdi32.DeleteObject(hF)

class Physics:
    """Math Library for collision logic."""
    @staticmethod
    def circle_collide(c1, c2):
        # Using distance squared to avoid costly sqrt()
        dx = (c1.x + c1.r) - (c2.x + c2.r)
        dy = (c1.y + c1.r) - (c2.y + c2.r)
        return (dx*dx + dy*dy) < (c1.r + c2.r)**2

    @staticmethod
    def resolve_elastic(b1, b2):
        # 1. Geometry
        c1x, c1y = b1.x + b1.r, b1.y + b1.r
        c2x, c2y = b2.x + b2.r, b2.y + b2.r
        dx, dy = c1x - c2x, c1y - c2y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist == 0: return

        # 2. MTD (Minimum Translation Distance) to un-stick balls
        overlap = 0.5 * (dist - (b1.r + b2.r))
        b1.x -= overlap * (dx / dist); b1.y -= overlap * (dy / dist)
        b2.x += overlap * (dx / dist); b2.y += overlap * (dy / dist)

        # 3. Normal and Tangent Vectors
        nx, ny = dx / dist, dy / dist
        tx, ty = -ny, nx
        
        # 4. Dot Product Projection
        dpTan1 = b1.vx * tx + b1.vy * ty
        dpTan2 = b2.vx * tx + b2.vy * ty
        dpNorm1 = b1.vx * nx + b1.vy * ny
        dpNorm2 = b2.vx * nx + b2.vy * ny
        
        # 5. Swap Normal Momentum (Elastic Bounce)
        m1, m2 = dpNorm2, dpNorm1
        
        # 6. Recombine Vectors
        b1.vx = tx * dpTan1 + nx * m1; b1.vy = ty * dpTan1 + ny * m1
        b2.vx = tx * dpTan2 + nx * m2; b2.vy = ty * dpTan2 + ny * m2

class WindowEngine:
    """Main Game Loop Manager using Windows Message Pump."""
    def __init__(self, title, w, h, bg):
        self.w, self.h, self.bg = w, h, bg
        self.objs = []; self._reg(title)
        
    def add(self, o): self.objs.append(o)
    
    def _reg(self, t):
        self.wp = WNDPROCTYPE(self._proc)
        
        # FIX: Use kernel32.GetModuleHandleW instead of user32
        h_inst = kernel32.GetModuleHandleW(None)
        
        # FIX: Manually build WNDCLASS to avoid wintypes error
        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = self.wp
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = h_inst
        wc.hIcon = 0
        wc.hCursor = user32.LoadCursorW(None, 32512)
        wc.hbrBackground = 0
        wc.lpszMenuName = None
        wc.lpszClassName = "GE_" + str(random.randint(0,9999))

        user32.RegisterClassW(ctypes.byref(wc))
        self.hw = user32.CreateWindowExW(0, wc.lpszClassName, t, WS_OVERLAPPEDWINDOW, 
                                         CW_USEDEFAULT, CW_USEDEFAULT, self.w, self.h, 
                                         None, None, h_inst, None)
        user32.SetTimer(self.hw, 1, 16, None) # 16ms Timer (~60FPS)

    def _proc(self, h, m, w, l):
        if m == WM_DESTROY: 
            # FIX: Close all MCI threads on exit
            for sound in ACTIVE_SOUNDS:
                winmm.mciSendStringW(f"close {sound.alias}", None, 0, 0)
            user32.PostQuitMessage(0)
            return 0
        if m == WM_TIMER: 
            r = RECT(); user32.GetClientRect(h, ctypes.byref(r))
            for o in self.objs: o.update(r.right, r.bottom)
            user32.InvalidateRect(h, None, False); return 0
        if m == WM_PAINT:
            p = PAINTSTRUCT(); dc = user32.BeginPaint(h, ctypes.byref(p))
            r = RECT(); user32.GetClientRect(h, ctypes.byref(r))
            # Double Buffering Logic
            mdc = gdi32.CreateCompatibleDC(dc)
            mb = gdi32.CreateCompatibleBitmap(dc, r.right, r.bottom); ob = gdi32.SelectObject(mdc, mb)
            br = gdi32.CreateSolidBrush(self.bg); user32.FillRect(mdc, ctypes.byref(r), br); gdi32.DeleteObject(br)
            for o in self.objs: o.draw(mdc)
            gdi32.BitBlt(dc, 0, 0, r.right, r.bottom, mdc, 0, 0, SRCCOPY)
            gdi32.SelectObject(mdc, ob); gdi32.DeleteObject(mb); gdi32.DeleteDC(mdc); user32.EndPaint(h, ctypes.byref(p))
            return 0
        return user32.DefWindowProcW(h, m, w, l)

    def run(self):
        user32.ShowWindow(self.hw, SW_SHOW); user32.UpdateWindow(self.hw)
        m = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(m), None, 0, 0) != 0: 
            user32.TranslateMessage(ctypes.byref(m)); user32.DispatchMessageW(ctypes.byref(m))

class Box:
    def __init__(self, x, y, w, h, c): self.x, self.y, self.w, self.h, self.c = x, y, w, h, c
    def update(self, sw, sh): pass
    def draw(self, dc):
        b = gdi32.CreateSolidBrush(self.c); ob = gdi32.SelectObject(dc, b)
        gdi32.Rectangle(dc, int(self.x), int(self.y), int(self.x+self.w), int(self.y+self.h))
        gdi32.SelectObject(dc, ob); gdi32.DeleteObject(b)
class Circle(Box):
    def __init__(self, x, y, r, c): super().__init__(x, y, r*2, r*2, c); self.r = r
    def draw(self, dc):
        b = gdi32.CreateSolidBrush(self.c); ob = gdi32.SelectObject(dc, b)
        gdi32.Ellipse(dc, int(self.x), int(self.y), int(self.x+self.w), int(self.y+self.h))
        gdi32.SelectObject(dc, ob); gdi32.DeleteObject(b)

# =================================================================================
# PART 3: AUDIO ENGINE (SOFTWARE LOOPING & LERP)
# =================================================================================

class MCI:
    """Communicates with winmm.dll to play audio strings."""
    @staticmethod
    def get_status(alias):
        buf = ctypes.create_unicode_buffer(255)
        winmm.mciSendStringW(f"status {alias} mode", buf, 255, 0)
        return buf.value

class Sound:
    def __init__(self, filename):
        self.filename = os.path.abspath(filename)
        self.alias = "snd_" + str(random.randint(0, 999999))
        self.is_looping = False
        if os.path.exists(self.filename):
            winmm.mciSendStringW(f'open "{self.filename}" type waveaudio alias {self.alias}', None, 0, 0)
            ACTIVE_SOUNDS.append(self)
        else:
            print(f"ERROR: File not found {self.filename}")

    def play(self, loop=False):
        # Using software loop instead of hardware 'repeat'
        winmm.mciSendStringW(f'play {self.alias} from 0', None, 0, 0)
        self.is_looping = loop

    def update(self, sw, sh):
        """Must be called in the game loop to handle looping manually."""
        if self.is_looping and MCI.get_status(self.alias) == "stopped":
            winmm.mciSendStringW(f'play {self.alias} from 0', None, 0, 0)

class Synth:
    SR = 44100; NOTES = {}; names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']; base = 55.0
    for o in range(1, 8):
        for i, n in enumerate(names): NOTES[f"{n}{o}"] = base * (2 ** (((o*12+i)-(21))/12.0))
    NOTES['p'] = 0.0
    
    @staticmethod
    def tone(note, ms, vol=1.0, type='sine'):
        f = Synth.NOTES.get(note, 0); ns = int(Synth.SR * ms / 1000); buf = bytearray()
        for i in range(ns):
            t = i/Synth.SR
            val = math.sin(2*math.pi*f*t) if f > 0 else 0
            buf.append(int((val * vol * 127) + 128))
        return buf
    
    @staticmethod
    def save(fname, data):
        sz = len(data)
        h = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36+sz, b'WAVE', b'fmt ', 16, 1, 1, 44100, 44100, 1, 8, b'data', sz)
        try: 
            with open(fname, 'wb') as f: f.write(h); f.write(data)
        except PermissionError: 
            print(f"WARN: {fname} locked.")

class Sampler:
    """UPDATED: Uses Linear Interpolation (Lerp) for smooth pitch shifting."""
    def __init__(self, filename, base_note='C3'):
        self.base_freq = Synth.NOTES.get(base_note, 130.81)
        self.data = [128]*1000
        try:
            with wave.open(filename, 'rb') as wf:
                raw = wf.readframes(wf.getnframes())
                if wf.getsampwidth() == 1: self.data = list(raw)
        except: pass

    def get_bytes(self, target_freq, duration_ms, volume=1.0):
        n_output = int(Synth.SR * duration_ms / 1000)
        step = target_freq / self.base_freq if target_freq > 0 else 0
        out, idx, dlen = bytearray(), 0.0, len(self.data)
        
        for _ in range(n_output):
            # --- LINEAR INTERPOLATION (LERP) ALGORITHM ---
            idx_i = int(idx)
            idx_f = idx - idx_i # Fractional part
            
            # Normalize to signed space (-128 to 127) for math
            s1 = self.data[idx_i % dlen] - 128
            s2 = self.data[(idx_i + 1) % dlen] - 128
            
            # Interpolate: val = start + (end - start) * percent
            interpolated = s1 + (s2 - s1) * idx_f
            
            # Normalize back to unsigned space (0 to 255)
            final_val = int((interpolated * volume) + 128)
            out.append(max(0, min(255, final_val)))
            
            idx += step
        return out

class Melody:
    @staticmethod
    def compile(fname, bpm, notes):
        d, ms = bytearray(), 60000 / bpm
        print(f"Compiling {fname}...")
        
        # Robust string cleaning to prevent ValueErrors
        clean_notes = notes.replace('(', '').replace(')', '').replace(' ', '')
        
        for i in clean_notes.split(','):
            if '_' in i:
                n, l = i.split('_'); nu, de = map(float, l.split('/')); dur = (nu/de)*ms*4
                d.extend(Synth.tone(n, dur*0.9, 0.6)); d.extend(Synth.tone('p', dur*0.1))
        Synth.save(fname, d)

# =================================================================================
# PART 4: RUNTIME DEMO
# =================================================================================

class Ball(Circle):
    def __init__(self, x, y, r, c, vx, vy, sfx):
        super().__init__(x, y, r, c); self.vx, self.vy, self.sfx = vx, vy, sfx; self.target = None
    def update(self, sw, sh):
        self.x += self.vx; self.y += self.vy
        
        hit = False
        if self.x <= 0: self.x=0; self.vx*=-1; hit=True
        elif self.x+self.w>=sw: self.x=sw-self.w; self.vx*=-1; hit=True
        if self.y <= 0: self.y=0; self.vy*=-1; hit=True
        elif self.y+self.h>=sh: self.y=sh-self.h; self.vy*=-1; hit=True
        
        if hit and self.sfx: self.sfx.play()
            
        if self.target and getattr(self, 'id', 0) == 1:
            if Physics.circle_collide(self, self.target):
                Physics.resolve_elastic(self, self.target)
                if self.sfx: self.sfx.play()

if __name__ == "__main__":
    # FIX: Use Dynamic Filenames to prevent Permission/File Lock errors
    sid = str(random.randint(1000, 9999))
    print(f"Session: {sid} | Generating Audio...")
    
    f_bounce = f"bounce_{sid}.wav"; f_music = f"music_{sid}.wav"
    Synth.save(f_bounce, Synth.tone('C4', 50, 0.4, 'noise'))
    Melody.compile(f_music, 180, "(C4_1/4, E4_1/4, G4_1/2, C5_1/4, G4_1/4, E4_1/2)")
    
    # CRITICAL: Wait for OS to flush files to disk
    time.sleep(1.0)
    
    game = WindowEngine("Engine v1.2 - High Fidelity", 800, 600, RGB(30,30,30))
    sfx = Sound(f_bounce)
    bgm = Sound(f_music)
    
    # Enable Software Looping
    bgm.play(loop=True)
    
    # Hook the BGM update to the game loop
    bgm.draw = lambda dc: None 
    game.add(bgm)
    
    b1 = Ball(200, 300, 40, RGB(255,0,0), 6, 4, sfx)
    b2 = Ball(600, 300, 40, RGB(0,0,255), -5, -3, sfx)
    
    b1.id = 1; b2.id = 2
    b1.target = b2; b2.target = b1
    
    game.add(b1)
    game.add(b2)
    
    print("Engine Running.")
    game.run()
