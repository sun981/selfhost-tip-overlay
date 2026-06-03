"""
Generate a default alert chime for the overlay — stdlib only (no ffmpeg/lame).
Writes app/overlay/sounds/alert.wav (16-bit PCM, browser-safe).
Run: python3 tools/make_alert_sound.py
Replace the .wav with your own sound anytime; overlay just plays whatever is there.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "app" / "overlay" / "sounds" / "alert.wav"


def tone(freq: float, dur: float, amp: float = 0.5) -> list[float]:
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # exponential decay + 5ms fade-in to kill clicks
        env = math.exp(-3.0 * t)
        fade = min(1.0, t / 0.005)
        out.append(amp * env * fade * math.sin(2 * math.pi * freq * t))
    return out


def main() -> None:
    # Two-note rising chime: A5 -> D6 (pleasant "ding-dong")
    samples = tone(880.0, 0.18) + tone(1174.66, 0.42)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in samples
        )
        w.writeframes(frames)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(samples)/SAMPLE_RATE:.2f}s)")


if __name__ == "__main__":
    main()
