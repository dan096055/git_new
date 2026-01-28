"""
===================================================================================
                                  DOCUMENTATION
===================================================================================
[GRAPHICS SYSTEM]
1. WindowEngine(title, width, height, bg_color) -> Main Window.
2. Text.draw(hdc, x, y, text, color, size) -> Draw text (Bottom-Left).
3. Text.draw_center(hdc, x, y, text, color, size) -> Draw text (Center).
4. Input.get_key(code) -> Returns True/False.

[AUDIO SYSTEM - BUILT-IN SYNTH]
1. Synth.play_note(note, duration_ms, wave_type, volume)
   -> wave_type: 'sine', 'square', 'triangle', 'sawtooth', 'noise'.

[AUDIO SYSTEM - SAMPLER]
1. Sampler(filename, base_note)
   -> Loads a .wav file to be used as an instrument.
   -> base_note: The note pitch of the original audio file (e.g., 'C3').
   -> The engine will automatically pitch-shift this sample to play any note.

2. Melody(name, bpm, notes_string)
   -> .play(instrument, loop, volume, gate)
      * instrument: Can be a string ('sine') OR a Sampler object.
===================================================================================
"""

import ctypes
from ctypes import wintypes
import math
import struct
import random
import wave

# =================================================================================
# PART 1: SYSTEM CORE (Windows API Interfacing)
# =================================================================================

# Load the core Windows libraries
user32 = ctypes.windll.user32    # Handles windows, menus, and input
gdi32 = ctypes.windll.gdi32      # Graphics Device Interface (drawing shapes/text)
kernel32 = ctypes.windll.kernel32 # System memory and module handling
winmm = ctypes.windll.winmm      # Windows Multimedia for audio playback

# Define C-compatible types for 64-bit/32-bit compatibility
if ctypes.sizeof(ctypes.c_void_p) == 8: 
    LRESULT = ctypes.c_longlong # 64-bit return type
else: 
    LRESULT = ctypes.c_long     # 32-bit return type

# Patch missing Windows types in the wintypes module
if not hasattr(wintypes, 'HCURSOR'): wintypes.HCURSOR = wintypes.HANDLE
if not hasattr(wintypes, 'HBRUSH'): wintypes.HBRUSH = wintypes.HANDLE
if not hasattr(wintypes, 'HICON'): wintypes.HICON = wintypes.HANDLE
if not hasattr(wintypes, 'LPCWSTR'): wintypes.LPCWSTR = ctypes.c_wchar_p

# Windows System Constants
WS_OVERLAPPEDWINDOW = 0x00CF0000 # Standard window with title bar and borders
CW_USEDEFAULT = 0x80000000       # Let Windows decide window position
WM_DESTROY = 2                   # Message sent when window is closed
WM_PAINT = 0x000F                # Message sent when window needs redrawing
WM_TIMER = 0x0113                # Message sent by the internal clock (for 60fps)
SW_SHOW = 5                      # Command to make window visible
SRCCOPY = 0x00CC0020             # Exact copy flag for BitBlt (Drawing)
TRANSPARENT = 1                  # Draw text without a solid background box
SND_ASYNC = 0x0001               # Don't wait for sound to finish; play in background
SND_LOOP = 0x0008                # Repeat sound indefinitely
SND_FILENAME = 0x00020000        # Tell PlaySound that we are passing a file path

# C-Structures required by Windows OS to track window state and drawing
class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wintypes.HANDLE), ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

# Function Prototype definitions (Ensures data is passed to Windows correctly)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
gdi32.SetTextColor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
gdi32.SetBkMode.argtypes = [wintypes.HANDLE, ctypes.c_int]
gdi32.CreateFontW.argtypes = [ctypes.c_int]*5 + [wintypes.DWORD]*8 + [wintypes.LPCWSTR]
gdi32.TextOutW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
gdi32.GetTextExtentPoint32W.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)]
gdi32.SelectObject.restype = wintypes.HANDLE

def RGB(r, g, b): 
    """Converts standard 0-255 Red, Green, Blue to a Windows COLORREF."""
    return r | (g << 8) | (b << 16)

# =================================================================================
# PART 2: GRAPHICS & INPUT (The Frontend)
# =================================================================================

class Input:
    """Handles keyboard state detection using Windows Virtual-Key codes."""
    K_A, K_D, K_W, K_S, SPACE = 0x41, 0x44, 0x57, 0x53, 0x20
    
    @staticmethod
    def get_key(c): 
        """Returns True if the key code 'c' is currently pressed."""
        return (user32.GetAsyncKeyState(c) & 0x8000) != 0

class Text:
    """GDI Text helper to handle fonts and drawing on the device context (HDC)."""
    @staticmethod
    def _font(hdc, size, color):
        """Internal: Creates a temporary Windows font object."""
        gdi32.SetBkMode(hdc, TRANSPARENT) # No background box behind text
        gdi32.SetTextColor(hdc, color)
        return gdi32.CreateFontW(size, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 0, "Arial")

    @staticmethod
    def draw(hdc, x, y, txt, col, sz=20):
        """Draws text at (x, y) coordinates."""
        hF = Text._font(hdc, sz, col) 
        oF = gdi32.SelectObject(hdc, hF) # Load font into GDI
        s = SIZE() 
        gdi32.GetTextExtentPoint32W(hdc, txt, len(txt), ctypes.byref(s))
        gdi32.TextOutW(hdc, int(x), int(y-s.cy), txt, len(txt))
        gdi32.SelectObject(hdc, oF) # Restore original font
        gdi32.DeleteObject(hF)      # Clean up memory

    @staticmethod
    def draw_center(hdc, x, y, txt, col, sz=20):
        """Draws text centered exactly at (x, y)."""
        hF = Text._font(hdc, sz, col) 
        oF = gdi32.SelectObject(hdc, hF)
        s = SIZE() 
        gdi32.GetTextExtentPoint32W(hdc, txt, len(txt), ctypes.byref(s))
        # Offset coordinates by half the width and height of the text
        gdi32.TextOutW(hdc, int(x - s.cx/2), int(y - s.cy/2), txt, len(txt))
        gdi32.SelectObject(hdc, oF)
        gdi32.DeleteObject(hF)

class WindowEngine:
    """The Main Engine Controller. Manages the window, frame-rate, and redraws."""
    def __init__(self, title, w, h, bg):
        self.w, self.h, self.bg = w, h, bg
        self.objs = [] # List of entities to update and draw
        self._reg(title)
        
    def add(self, o): 
        """Adds an object to the game loop."""
        self.objs.append(o)
    
    def _reg(self, t):
        """Internal: Registers a new Window Class with the Windows OS."""
        self.wp = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)(self._proc)
        
        class W(ctypes.Structure): 
            _fields_=[("cb",wintypes.UINT),("st",wintypes.UINT),("lp",ctypes.c_void_p),
                      ("ce",ctypes.c_int),("cw",ctypes.c_int),("hi",wintypes.HINSTANCE),
                      ("ho",wintypes.HICON),("hc",wintypes.HCURSOR),("hb",wintypes.HBRUSH),
                      ("lm",wintypes.LPCWSTR),("ln",wintypes.LPCWSTR),("hs",wintypes.HICON)]
        
        # Define window properties (Cursor, ClassName, etc.)
        w = W(ctypes.sizeof(W), 0, ctypes.cast(self.wp, ctypes.c_void_p), 0, 0, 
              kernel32.GetModuleHandleW(None), None, user32.LoadCursorW(None, 32512), 
              None, None, "E_"+str(random.randint(0,999)), None)
        
        user32.RegisterClassExW(ctypes.byref(w))
        
        # Actually create the window on the screen
        self.hw = user32.CreateWindowExW(0, w.ln, t, WS_OVERLAPPEDWINDOW, 
                                         CW_USEDEFAULT, CW_USEDEFAULT, 
                                         self.w, self.h, 
                                         None, None, w.hi, None)
        # Set a timer to trigger redrawing every ~16ms (for 60fps)
        user32.SetTimer(self.hw, 1, 16, None)

    def _proc(self, h, m, w, l):
        """The 'Message Pump' - handles all system events."""
        if m == WM_DESTROY: 
            winmm.sndPlaySoundW(None, 0) # Stop any sounds when closing
            user32.PostQuitMessage(0)
            return 0
            
        if m == WM_TIMER: 
            # Logic Update Phase
            r = RECT(); user32.GetClientRect(h, ctypes.byref(r))
            for o in self.objs: o.update(r.right, r.bottom)
            # Tell Windows the screen is 'dirty' and needs to be repainted
            user32.InvalidateRect(h, None, False)
            return 0
            
        if m == WM_PAINT:
            # Rendering Phase (using Double Buffering to prevent flicker)
            p = PAINTSTRUCT(); dc = user32.BeginPaint(h, ctypes.byref(p))
            r = RECT(); user32.GetClientRect(h, ctypes.byref(r))
            
            # Create a 'Memory Context' (Off-screen canvas)
            mdc = gdi32.CreateCompatibleDC(dc)
            mb = gdi32.CreateCompatibleBitmap(dc, r.right, r.bottom)
            ob = gdi32.SelectObject(mdc, mb)
            
            # Clear background
            br = gdi32.CreateSolidBrush(self.bg)
            user32.FillRect(mdc, ctypes.byref(r), br)
            gdi32.DeleteObject(br)
            
            # Draw all game objects onto the off-screen canvas
            for o in self.objs: o.draw(mdc)
            
            # Copy the final image from memory to the actual screen instantly
            gdi32.BitBlt(dc, 0, 0, r.right, r.bottom, mdc, 0, 0, SRCCOPY)
            
            # Memory Cleanup
            gdi32.SelectObject(mdc, ob); gdi32.DeleteObject(mb); gdi32.DeleteDC(mdc) 
            user32.EndPaint(h, ctypes.byref(p))
            return 0
        return user32.DefWindowProcW(h, m, w, l)

    def run(self):
        """Starts the infinite Windows message loop."""
        user32.ShowWindow(self.hw, SW_SHOW) 
        user32.UpdateWindow(self.hw)
        m = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(m), None, 0, 0) != 0: 
            user32.TranslateMessage(ctypes.byref(m)) 
            user32.DispatchMessageW(ctypes.byref(m))

class Box:
    """A standard game entity (Rectangle)."""
    def __init__(self, x, y, w, h, c): 
        self.x, self.y, self.w, self.h, self.c = x, y, w, h, c
    def update(self, sw, sh): pass
    def draw(self, dc):
        b = gdi32.CreateSolidBrush(self.c)
        ob = gdi32.SelectObject(dc, b)
        gdi32.Rectangle(dc, int(self.x), int(self.y), int(self.x+self.w), int(self.y+self.h))
        gdi32.SelectObject(dc, ob) 
        gdi32.DeleteObject(b)

# =================================================================================
# PART 3: AUDIO ENGINE (Sound Logic)
# =================================================================================

class Audio:
    """Helper for playing existing sound files."""
    @staticmethod
    def play_file(fname):
        """Plays a WAV or MP3 file in the background."""
        alias = "a_" + str(random.randint(0,9999))
        winmm.mciSendStringW(f'open "{fname}" alias {alias}', None, 0, 0)
        winmm.mciSendStringW(f'play {alias}', None, 0, 0)

class Synth:
    """Mathematical Sound Generator. Creates music from numbers."""
    SR = 44100 # Standard Sample Rate (44.1 kHz)
    NOTES = {}
    names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    base_a1 = 55.0 # Hz
    
    # Pre-calculate a frequency table for all notes (A1 to B7)
    for oct in range(1, 8):
        for i, name in enumerate(names):
            # Formula: Frequency = 440 * 2^(n/12)
            abs_semitone = (oct * 12 + i) - (1 * 12 + 9)
            freq = base_a1 * (2 ** (abs_semitone / 12.0))
            NOTES[f"{name}{oct}"] = freq
    NOTES['p'] = 0.0 # 'p' stands for Pause (Frequency of 0)

    @staticmethod
    def _gen_bytes(freq, ms, type='sine', vol=1.0):
        """Generates raw PCM byte data for a specific wave shape."""
        n_samp = int(Synth.SR * ms / 1000)
        if freq == 0: return bytearray([128] * n_samp) # Silence
        
        buf = bytearray()
        vol = max(0.0, min(1.0, vol))
        for i in range(n_samp):
            t = float(i) / Synth.SR
            # Math for different wave forms
            if type == 'sine': val = math.sin(2*math.pi*freq*t)
            elif type == 'square': val = 0.5 if math.sin(2*math.pi*freq*t)>0 else -0.5
            elif type == 'triangle': val = 2*abs(2*(freq*t - math.floor(freq*t + 0.5))) - 1
            elif type == 'sawtooth': val = 2*(freq*t - math.floor(freq*t + 0.5))
            elif type == 'noise': val = random.uniform(-0.5, 0.5)
            
            # Convert -1.0..1.0 float to 0..255 byte
            sample = int((val * vol * 127) + 128)
            buf.append(sample)
        return buf

    @staticmethod
    def _write_wav(fname, data):
        """Wraps raw PCM bytes into a valid RIFF/WAV file format."""
        sz = len(data)
        h = struct.pack('<4sI4s4sIHHIIHH4sI', 
                        b'RIFF', 36+sz, b'WAVE', b'fmt ', 16, 1, 1, Synth.SR, Synth.SR, 1, 8, b'data', sz)
        with open(fname, 'wb') as f: f.write(h); f.write(data)

    @staticmethod
    def play_note(note_name, ms, type='sine', volume=1.0):
        """Generates and plays a single tone immediately."""
        f = Synth.NOTES.get(note_name, 0)
        data = Synth._gen_bytes(f, ms, type, volume)
        fn = "temp_tone.wav"
        Synth._write_wav(fn, data)
        winmm.sndPlaySoundW(fn, SND_FILENAME | SND_ASYNC)

class Sampler:
    """Takes a single recording and 'stretches' it to play different pitches."""
    def __init__(self, filename, base_note='C3'):
        # Frequency of the original recording
        self.base_freq = Synth.NOTES.get(base_note, 130.81)
        self.data = []
        try:
            with wave.open(filename, 'rb') as wf:
                raw = wf.readframes(wf.getnframes())
                width = wf.getsampwidth()
                # Normalize any WAV to 8-bit unsigned for the engine
                if width == 1: self.data = list(raw)
                elif width == 2: 
                    shorts = struct.unpack("<" + "h" * (len(raw)//2), raw)
                    self.data = [int((s/32768)*127 + 128) for s in shorts]
        except:
            print(f"Error loading sample: {filename}")
            self.data = [128] * 1000

    def get_bytes(self, target_freq, duration_ms, volume=1.0):
        """Pitch-shifter logic (Resampling)."""
        n_output = int(Synth.SR * duration_ms / 1000)
        if target_freq == 0: return bytearray([128] * n_output)

        # Ratio of target frequency to recorded frequency
        step = target_freq / self.base_freq
        out = bytearray()
        idx = 0.0
        data_len = len(self.data)
        for _ in range(n_output):
            # Pick a sample point in the original audio
            sample_idx = int(idx) % data_len
            val = int(((self.data[sample_idx] - 128) * volume) + 128)
            out.append(max(0, min(255, val)))
            idx += step # Move faster through the data for higher notes
        return out

class Melody:
    """Interpreter that converts music strings into a full audio file."""
    def __init__(self, name, bpm, note_str):
        self.n, self.bpm = name, bpm
        self.data = self._parse(note_str)
        
    def _parse(self, s):
        """Parses '(C4_1/4, ...)' into frequencies and millisecond durations."""
        s = s.replace('(', '').replace(')', '').replace(' ', '')
        seq = []
        ms_per_beat = 60000 / self.bpm
        for item in s.split(','):
            if '_' not in item: continue
            note, dur_str = item.split('_')
            num, den = map(float, dur_str.split('/'))
            dur_ms = (num / den) * ms_per_beat * 4 
            freq = Synth.NOTES.get(note, 0)
            seq.append((freq, dur_ms))
        return seq

    def play(self, instrument='sine', loop=False, volume=1.0, gate=0.9):
        """Generates the whole song as a single WAV and plays it."""
        full_dat = bytearray()
        print(f"Synthesizing: {self.n}...")
        for f, d in self.data:
            active_ms = d * gate
            gap_ms = d * (1.0 - gate) # Separation between notes
            
            # Use Sampler if an object is passed, otherwise use Synth
            if isinstance(instrument, Sampler):
                full_dat.extend(instrument.get_bytes(f, active_ms, volume))
            else:
                full_dat.extend(Synth._gen_bytes(f, active_ms, instrument, volume))
            full_dat.extend(Synth._gen_bytes(0, gap_ms, 'sine', volume))
        
        fn = f"{self.n}.wav"
        Synth._write_wav(fn, full_dat)
        flags = SND_FILENAME | SND_ASYNC
        if loop: flags = flags | SND_LOOP
        winmm.sndPlaySoundW(fn, flags)

# =================================================================================
# PART 4: RUNTIME
# =================================================================================

class Player(Box):
    """Your controllable character."""
    def update(self, sw, sh):
        if Input.get_key(Input.K_A): self.x -= 5
        if Input.get_key(Input.K_D): self.x += 5
        if Input.get_key(Input.K_W): self.y -= 5
        if Input.get_key(Input.K_S): self.y += 5
        
        # Keep player in window bounds
        self.x = max(0, min(self.x, sw - self.w))
        self.y = max(0, min(self.y, sh - self.h))
        
        if Input.get_key(Input.SPACE):
            Synth.play_note('C4', 100, 'sawtooth', volume=0.5)

    def draw(self, dc):
        super().draw(dc)
        Text.draw_center(dc, self.x + self.w/2, self.y + self.h/2, "P1", RGB(0,0,0), 16)

def create_dummy_instrument_file(filename):
    """Utility to generate a test wav file."""
    data = Synth._gen_bytes(130.81, 1000, 'sine', 1.0)
    Synth._write_wav(filename, data)

if __name__ == "__main__":
    # Create the window
    game = WindowEngine("Dark is the Night - Sampler Edition", 800, 600, RGB(30,30,30))
    game.add(Player(300, 300, 50, 50, RGB(0,200,0)))
    
    # Setup the Sample-based Instrument
    create_dummy_instrument_file("my_instrument.wav")
    my_instrument = Sampler("my_instrument.wav", base_note='C3')

    # Arrangement of "Dark is the Night"
    dark_is_the_night = (
        "(A4_1/2, C5_1/4, B4_1/4, A4_1/1, p_1/4, "
        "F4_1/4, G4_1/4, A4_1/3, G4_1/3, F4_1/3, F4_1/4, E4_1/3, D#4_1/3, E4_1/2, p_1/2, "
        "D4_1/4, E4_1/4, F4_1/3, E4_1/3, D4_1/3, A4_1/2, E4_1/4, D4_1/4, C4_1/2, p_1/2, "
        "B3_1/4, C4_1/4, D4_1/2, C4_1/4, B3_1/4, B3_1/2, A3_1/1, p_1/2)"
    )
    
    # Process and play melody
    m = Melody("DarkIsTheNight", 144, dark_is_the_night)
    m.play(instrument=my_instrument, loop=True, volume=0.2, gate=0.95)
    
    # Start the engine
    game.run()
