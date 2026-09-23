import sys, wave
import numpy as np

# Soft ambient bed in D major: warm pad + sub + sparse bell notes. Usage: music.py <seconds> <out.wav>
SR = 48000
dur = float(sys.argv[1]); out = sys.argv[2]
rng = np.random.default_rng(7)
n = int(dur * SR); t = np.arange(n) / SR
L = np.zeros(n); R = np.zeros(n)

def hz(m): return 440 * 2 ** ((m - 69) / 12)

# D(add9) - Bm7 - Gmaj7 - A(sus4), 6 s per chord
CHORDS = [[38, 45, 50, 52, 54], [35, 42, 47, 50, 54], [31, 38, 43, 47, 54], [33, 40, 45, 50, 52]]
BAR = 6.0

def env(length, a, r):
    e = np.ones(length); ai, ri = min(int(a * SR), length // 2), min(int(r * SR), length // 2)
    e[:ai] = np.sin(np.linspace(0, np.pi / 2, ai)) ** 2
    e[-ri:] *= np.cos(np.linspace(0, np.pi / 2, ri)) ** 2
    return e

def pad_voice(f, length, pan):
    tt = np.arange(length) / SR; s = np.zeros(length)
    for det in (-0.12, 0.0, 0.11):              # three detuned voices, cents-ish
        ff = f * 2 ** (det / 12)
        ph = rng.uniform(0, 2 * np.pi)
        for h, amp in ((1, 1.0), (2, 0.28), (3, 0.09), (4, 0.04)):
            s += amp * np.sin(2 * np.pi * ff * h * tt + ph * h)
    s *= 1 + 0.08 * np.sin(2 * np.pi * 0.23 * tt + rng.uniform(0, 6))   # slow swell
    return s * (1 - pan), s * pan

bar = 0
while bar * BAR < dur:
    ch = CHORDS[bar % 4]; s0 = int(bar * BAR * SR)
    length = min(int((BAR + 2.5) * SR), n - s0)   # 2 s overlap into next chord
    if length <= SR: break
    e = env(length, 2.0, 2.5)
    for i, m in enumerate(ch):
        l, r = pad_voice(hz(m), length, 0.3 + 0.1 * i)
        L[s0:s0 + length] += 0.11 * l * e; R[s0:s0 + length] += 0.11 * r * e
    sub = np.sin(2 * np.pi * hz(ch[0]) * np.arange(length) / SR) * e * 0.18
    L[s0:s0 + length] += sub; R[s0:s0 + length] += sub
    # sparse bell notes: 3 per bar, chord tones up an octave
    for k, beat in ():
        bs = s0 + int(beat * SR); bl = min(int(3.5 * SR), n - bs)
        if bl <= 0: continue
        f = hz(ch[(k * 2 + bar) % len(ch)] + 12); tt = np.arange(bl) / SR
        b = (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt * 3)) * np.exp(-tt * 1.3)
        b[:240] *= np.linspace(0, 1, 240)
        pan = 0.35 + 0.3 * ((k + bar) % 3) / 2
        L[bs:bs + bl] += 0.025 * b * (1 - pan) * 2; R[bs:bs + bl] += 0.025 * b * pan * 2
    bar += 1

# simple stereo reverb: a few feedback-free early reflections + long diffuse tail
def verb(x, delays, gains):
    y = x.copy()
    for d, g in zip(delays, gains):
        di = int(d * SR); y[di:] += g * x[:-di]
    return y
L = verb(L, (0.031, 0.067, 0.113, 0.179, 0.263, 0.391), (0.35, 0.3, 0.25, 0.2, 0.15, 0.1))
R = verb(R, (0.037, 0.073, 0.127, 0.191, 0.281, 0.417), (0.35, 0.3, 0.25, 0.2, 0.15, 0.1))

# gentle master fades
fi, fo = int(1.0 * SR), int(4.0 * SR)
for ch_ in (L, R):
    ch_[:fi] *= np.linspace(0, 1, fi)
    ch_[-fo:] *= np.linspace(1, 0, fo) ** 1.5
st = np.stack([L, R], 1); st /= np.abs(st).max() * 1.12
with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
