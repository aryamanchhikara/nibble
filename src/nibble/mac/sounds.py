"""Chiptune sound effects for the home page, synthesized on the fly (no files).

Square waves with a quick decay, like an old console's pulse channel. Muted
by default; the speaker button on the home page turns them on.
"""

from __future__ import annotations

import io
import struct
import wave

from AppKit import NSSound
from Foundation import NSData

RATE = 22050
VOLUME = 0.16

# name: [(frequency Hz, seconds), ...]
EFFECTS: dict[str, list[tuple[float, float]]] = {
    "move": [(880, 0.035), (1320, 0.04)],
    "toggle": [(660, 0.04), (990, 0.06)],
    "open": [(784, 0.05), (988, 0.08)],
    "back": [(660, 0.05), (440, 0.09)],
    "start": [(523, 0.07), (659, 0.07), (784, 0.07), (1047, 0.18)],
}


def synth(notes: list[tuple[float, float]]) -> bytes:
    """16-bit mono WAV bytes for a little sequence of square-wave notes."""
    frames = bytearray()
    for freq, seconds in notes:
        n = int(RATE * seconds)
        period = RATE / freq
        for i in range(n):
            env = (1 - i / n) ** 1.5  # quick decay
            high = (i % period) < period / 2
            frames += struct.pack("<h", int((1 if high else -1) * env * VOLUME * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    return buf.getvalue()


class Sounds:
    def __init__(self) -> None:
        self._sounds: dict[str, NSSound] = {}

    def play(self, name: str) -> None:
        notes = EFFECTS.get(name)
        if not notes:
            return
        sound = self._sounds.get(name)
        if sound is None:
            data = synth(notes)
            sound = NSSound.alloc().initWithData_(NSData.dataWithBytes_length_(data, len(data)))
            self._sounds[name] = sound
        sound.stop()
        sound.play()
