#!/usr/bin/env python3
"""Synthesises the game's sound effects (own work; the original's audio is not redistributable).
Writes assets/audio/<id>.ogg for every hook id in docs/AUDIO_HOOKS.md (WAV when ffmpeg is missing).
Requires numpy; uses ffmpeg (libvorbis) when available.  Usage: make_sounds.py [id ...] (default: all;
the noise is seeded and every sound draws in list order, so new sounds go at the end of the list)."""
import math
import os
import shutil
import struct
import subprocess
import sys
import wave

import numpy as np

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
# the package keeps assets beside source/ (source/tools/../../assets); a plain checkout of the cloud
# layout had tools/ beside assets/
OUT = next((d for d in (os.path.join(HERE, "..", "..", "assets", "audio"), os.path.join(HERE, "..", "assets", "audio"))
            if os.path.isdir(os.path.dirname(d))), os.path.join(HERE, "..", "assets", "audio"))
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(12345)


def t(dur):
    return np.arange(int(SR * dur)) / SR


def env_exp(dur, decay, attack=0.002):
    x = t(dur)
    e = np.exp(-x / decay)
    a = np.minimum(1.0, x / max(attack, 1e-4))
    return e * a


def env_adsr(dur, a=0.01, d=0.05, s=0.6, r=0.1):
    n = int(SR * dur)
    x = np.arange(n) / SR
    e = np.ones(n) * s
    na = int(SR * a)
    nd = int(SR * d)
    nr = int(SR * r)
    e[:na] = np.linspace(0, 1, na, endpoint=False) if na else e[:na]
    e[na:na + nd] = np.linspace(1, s, nd, endpoint=False) if nd else e[na:na + nd]
    if nr:
        e[-nr:] = np.linspace(e[-nr] if n > nr else s, 0, nr)
    return e


def sine(freq, dur, phase=0.0):
    x = t(dur)
    if callable(freq):
        f = freq(x)
        ph = 2 * np.pi * np.cumsum(f) / SR
    else:
        ph = 2 * np.pi * freq * x
    return np.sin(ph + phase)


def saw(freq, dur):
    x = t(dur)
    f = freq(x) if callable(freq) else np.full_like(x, freq)
    ph = np.cumsum(f) / SR
    return 2.0 * (ph - np.floor(ph + 0.5))


def square(freq, dur):
    return np.sign(sine(freq, dur) + 1e-9)


def noise(dur):
    return rng.uniform(-1, 1, int(SR * dur))


def sweep(f0, f1, dur, curve=1.0):
    """Frequency function from f0 to f1 over dur."""
    return lambda x: f0 + (f1 - f0) * np.clip(x / dur, 0, 1) ** curve


def lowpass(sig, cutoff):
    """One-pole low-pass; cutoff may be an array (per-sample)."""
    out = np.zeros_like(sig)
    c = np.full(len(sig), cutoff, dtype=np.float64) if np.isscalar(cutoff) else cutoff
    alpha = np.clip(2 * np.pi * c / SR, 0, 0.999)
    y = 0.0
    for i in range(len(sig)):
        y += alpha[i] * (sig[i] - y)
        out[i] = y
    return out


def highpass(sig, cutoff):
    return sig - lowpass(sig, cutoff)


def bandpass(sig, lo, hi):
    return highpass(lowpass(sig, hi), lo)


def crackle(dur, density=40, decay=0.004):
    n = int(SR * dur)
    out = np.zeros(n)
    for _ in range(int(density * dur)):
        i = rng.integers(0, n)
        ln = int(SR * decay * rng.uniform(0.5, 2.0))
        seg = noise(ln / SR) * env_exp(ln / SR, decay / 2)[:ln]
        end = min(n, i + len(seg))
        out[i:end] += seg[:end - i] * rng.uniform(0.4, 1.0)
    return out


def mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[:len(p)] += p
    return out


def fit(sig, dur):
    n = int(SR * dur)
    return sig[:n] if len(sig) >= n else np.pad(sig, (0, n - len(sig)))


def soft(sig, drive=1.5):
    return np.tanh(sig * drive)


def write(name, sig, gain=0.9):
    peak = np.max(np.abs(sig)) or 1.0
    data = np.clip(sig / peak * gain, -1, 1)
    # short fade-out to avoid clicks
    nf = min(len(data), int(SR * 0.01))
    data[-nf:] *= np.linspace(1, 0, nf)
    wav = os.path.join(OUT, f"{name}.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack(f"<{len(data)}h", *(np.int16(data * 32767))))
    if shutil.which("ffmpeg"):
        ogg = os.path.join(OUT, f"{name}.ogg")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libvorbis", "-q:a", "4", ogg])
        if r.returncode == 0:
            os.remove(wav)
            return ogg
    return wav


def explosion(dur, low=55, bright=1.0, boom=1.0):
    n = noise(dur)
    cut = 6000 * bright * np.exp(-t(dur) / (dur * 0.35)) + 150
    body = lowpass(n, cut) * env_exp(dur, dur * 0.3)
    thump = sine(sweep(low * 1.6, low, dur * 0.5), dur) * env_exp(dur, dur * 0.22) * boom
    return soft(mix(body * 1.2, thump * 1.3, crackle(dur, 60, 0.003) * 0.4 * bright), 1.8)


def gun_pop(dur=0.1, cut=1800, thump=120):
    return soft(mix(lowpass(noise(dur), cut) * env_exp(dur, dur * 0.25), sine(sweep(thump * 2, thump, dur), dur) * env_exp(dur, dur * 0.2) * 0.8), 2.0)


def squeal(f0, f1, dur, wave_fn=sine, vib=12.0, vib_depth=0.05):
    x = t(dur)
    base = sweep(f0, f1, dur)
    freq = lambda xx: base(xx) * (1 + vib_depth * np.sin(2 * np.pi * vib * xx))
    return wave_fn(freq, dur) * env_adsr(dur, 0.01, 0.1, 0.5, dur * 0.4)


def chord_notes(notes, note_len, hold=0.4, wave_fn=sine, overlap=True):
    total = note_len * len(notes) + hold
    out = np.zeros(int(SR * total))
    for i, f in enumerate(notes):
        dur = (total - i * note_len) if overlap else note_len
        seg = (wave_fn(f, dur) * 0.6 + sine(f * 2, dur) * 0.25 + saw(f, dur) * 0.15) * env_adsr(dur, 0.01, 0.08, 0.55, min(0.5, dur * 0.5))
        start = int(SR * note_len * i)
        end = min(len(out), start + len(seg))
        out[start:end] += seg[:end - start]
    return out


sounds = {}
# bites and melee
sounds["ant_crunch"] = soft(mix(bandpass(noise(0.2), 900, 4500) * env_exp(0.2, 0.05), crackle(0.2, 90, 0.004), sine(sweep(220, 80, 0.2), 0.2) * env_exp(0.2, 0.05) * 0.5), 2)
sounds["savage_attack"] = soft(mix(sine(sweep(1400, 250, 0.25, 0.6), 0.25) * env_exp(0.25, 0.08), highpass(noise(0.25), 3000) * env_exp(0.25, 0.03) * 0.5), 1.5)
# guns
sounds["rocket_launch"] = soft(mix(lowpass(noise(0.7), 300 + 3000 * np.clip(t(0.7) / 0.25, 0, 1) * np.exp(-t(0.7) / 0.5)) * env_adsr(0.7, 0.02, 0.1, 0.6, 0.35), sine(sweep(70, 45, 0.7), 0.7) * env_exp(0.7, 0.3) * 0.7), 1.6)
sounds["minigun"] = gun_pop(0.1, 2200, 140)
sounds["shrapnel_fire"] = soft(mix(gun_pop(0.35, 1200, 90) * 1.0, highpass(crackle(0.35, 120, 0.003), 2500) * 0.8), 1.5)
sounds["cannon"] = explosion(0.55, 50, 0.6, 1.4)
sounds["sniper_fire"] = soft(mix(highpass(noise(0.08), 2500) * env_exp(0.08, 0.015) * 1.5, lowpass(noise(0.35), 900) * env_exp(0.35, 0.09) * 0.6), 2.2)
sounds["missile_launch"] = soft(mix(lowpass(noise(0.8), 800 + 2500 * np.clip(t(0.8) / 0.3, 0, 1)) * env_adsr(0.8, 0.03, 0.1, 0.7, 0.4), sine(sweep(200, 900, 0.8, 0.7), 0.8) * env_adsr(0.8, 0.02, 0.1, 0.5, 0.4) * 0.5), 1.5)
sounds["spear"] = soft(bandpass(noise(0.25), 600, 3500 * np.exp(-t(0.25) / 0.08) + 400) * env_exp(0.25, 0.05) * 2, 1.5)
sounds["star_launch"] = highpass(noise(0.2), 3500) * env_exp(0.2, 0.05)
sounds["star_hit"] = mix(*(sine(f, 0.18) * env_exp(0.18, 0.03 * (i + 1)) * 0.5 for i, f in enumerate((2400, 3650, 5100))))
sounds["machinegun"] = gun_pop(0.1, 1500, 110)
sounds["arrow"] = soft(mix(sine(440, 0.3) * env_exp(0.3, 0.06) * 0.8, sine(sweep(880, 440, 0.3), 0.3) * env_exp(0.3, 0.04) * 0.5, highpass(noise(0.3), 2500) * env_exp(0.3, 0.05) * 0.4), 1.4)
sounds["paralysis"] = soft(square(sweep(1200, 180, 0.5, 0.7), 0.5) * env_exp(0.5, 0.18) * (0.6 + 0.4 * np.sin(2 * np.pi * 28 * t(0.5))), 1.2) * 0.6
sounds["sonic"] = soft(mix(sine(sweep(280, 2100, 0.6, 0.8), 0.6), sine(sweep(560, 4200, 0.6, 0.8), 0.6) * 0.35) * env_adsr(0.6, 0.02, 0.1, 0.7, 0.3) * (0.7 + 0.3 * np.sin(2 * np.pi * 22 * t(0.6))), 1.3)
sounds["turret_mg"] = gun_pop(0.09, 2600, 160)
# impacts
sounds["explosion1"] = explosion(0.5, 70, 1.2, 0.9)
sounds["explosion2"] = explosion(0.8, 55, 0.9, 1.2)
sounds["explosion3"] = explosion(1.1, 45, 0.7, 1.5)
sounds["ricochet"] = soft(mix(sine(sweep(3200, 1100, 0.25, 0.5), 0.25) * env_exp(0.25, 0.07) * 0.8, highpass(noise(0.25), 3000) * env_exp(0.25, 0.015)), 1.4)
sounds["sniper_hit"] = soft(mix(lowpass(noise(0.2), 700) * env_exp(0.2, 0.04), sine(sweep(220, 120, 0.2), 0.2) * env_exp(0.2, 0.05)), 1.6)
sounds["brakebomb_explode"] = explosion(0.6, 90, 1.4, 0.8)
sounds["bouncebomb_explode"] = explosion(0.55, 120, 1.1, 1.0)
sounds["gobstopper_explode"] = soft(mix(explosion(0.7, 80, 1.0, 1.0), sine(sweep(900, 300, 0.7), 0.7) * env_exp(0.7, 0.12) * 0.4), 1.3)
sounds["bounce"] = sine(sweep(320, 140, 0.15), 0.15) * env_exp(0.15, 0.05)
# colonies and bits
sounds["colony_lost"] = soft(mix(saw(sweep(420, 55, 1.3, 0.8), 1.3) * 0.6, sine(sweep(210, 28, 1.3, 0.8), 1.3) * 0.5) * env_adsr(1.3, 0.02, 0.1, 0.8, 0.5), 1.3)
sounds["colony_explode"] = soft(mix(explosion(1.2, 40, 0.8, 1.6), crackle(1.2, 50, 0.006) * 0.6), 1.4)
sounds["colony_captured"] = mix(soft(saw(sweep(90, 620, 0.9, 1.2), 1.2) * env_adsr(1.2, 0.02, 0.2, 0.6, 0.4) * 0.5, 1.2), fit(chord_notes([880, 1320], 0.25, 0.5), 1.2) * 0.8 * np.concatenate([np.zeros(int(SR * 0.6)), np.ones(int(SR * 0.6))]))
sounds["bit_pickup"] = mix(sine(sweep(900, 1500, 0.2, 0.5), 0.2) * env_exp(0.2, 0.06), sine(2800, 0.2) * env_exp(0.2, 0.02) * 0.3)
sounds["ant_hole"] = soft(mix(lowpass(noise(0.7), 250) * env_adsr(0.7, 0.05, 0.1, 0.8, 0.3) * 1.5, sine(sweep(60, 40, 0.7), 0.7) * env_adsr(0.7, 0.05, 0.1, 0.8, 0.3), crackle(0.7, 30, 0.01) * 0.5), 1.8)
# deaths per family
sounds["death_ant"] = squeal(950, 380, 0.35)
sounds["death_beetle"] = soft(mix(squeal(520, 210, 0.45, square, 30, 0.08) * 0.5, lowpass(noise(0.45), 900) * env_exp(0.45, 0.12) * 0.6), 1.3)
sounds["death_spider"] = squeal(760, 240, 0.4, square, 18, 0.12) * 0.6
sounds["death_scorpion"] = soft(mix(squeal(420, 140, 0.5, saw, 9, 0.06) * 0.7, lowpass(noise(0.5), 600) * env_exp(0.5, 0.15) * 0.4), 1.4)
sounds["death_wasp"] = soft(square(sweep(330, 120, 0.5), 0.5) * env_exp(0.5, 0.15) * (0.6 + 0.4 * np.sin(2 * np.pi * 60 * t(0.5))), 1.2) * 0.6
sounds["death_neutral"] = squeal(620, 300, 0.35, sine, 14, 0.06)
# game events and interface
sounds["unit_ready"] = chord_notes([660, 990], 0.12, 0.3)
sounds["victory"] = soft(chord_notes([523.25, 659.25, 783.99, 1046.5], 0.28, 1.2), 1.1)
sounds["defeat"] = soft(mix(chord_notes([440, 349.23, 293.66, 277.18], 0.45, 1.0, wave_fn=saw) * 0.5, sine(55, 2.8) * env_adsr(2.8, 0.1, 0.3, 0.7, 0.8) * 0.6), 1.2)
sounds["ui_click"] = mix(highpass(noise(0.06), 2000) * env_exp(0.06, 0.008), sine(1500, 0.06) * env_exp(0.06, 0.012) * 0.6)
# added later (kept at the end so the sounds above keep their noise): the wasp colony's chain gun
# (the original's CHAINGUN; the ant colony's turret is a plain machine gun, turret_mg)
sounds["chaingun"] = soft(mix(gun_pop(0.12, 1900, 120), bandpass(noise(0.12), 2500, 6000) * env_exp(0.12, 0.03) * 0.5,
                              square(sweep(900, 700, 0.12), 0.12) * env_exp(0.12, 0.04) * 0.15), 1.8)

wanted = set(sys.argv[1:])
written = []
for name, sig in sounds.items():
    if not wanted or name in wanted:
        written.append(os.path.basename(write(name, sig)))
print(len(written), "sounds:", " ".join(sorted(written)))
