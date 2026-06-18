# Generating a QSO in a Jupyter Notebook

A practical guide to driving `procg_qso` from a notebook: make a QSO, hear it,
read the transcript, and tune every knob.

---

## 0. Setup (once per kernel)

Use the `cw` conda env as your notebook kernel. The package must be installed
(`pip install -e .` from the repo root). Then in a cell:

```python
import random
from procg_qso import (
    wordy_ragchew, ragchew_qso, contest_qso,   # content generators
    Station, channel_for_difficulty,           # voices + band conditions
    synthesize_qso, write_wav, write_mp3,       # render + save
)
from IPython.display import Audio               # in-notebook playback
```

---

## 1. The shortest path — generate, hear, read

```python
seed  = 7
turns = wordy_ragchew(random.Random(seed), wordiness=0.7, corpus_tail=3)

stations = [
    Station(wpm=25, farnsworth_wpm=18, freq=600),               # station 0
    Station(wpm=25, farnsworth_wpm=18, freq=610, amplitude=0.9), # station 1
]
ch = channel_for_difficulty(2, fs=11025)

sig, transcript = synthesize_qso(turns, stations, ch, seed=seed)

print(transcript)        # ground-truth text, line per over
Audio(sig, rate=ch.fs)   # renders an audio player in the notebook
```

`Audio(...)` must be the **last expression in the cell** to show the player.

---

## 2. The pipeline, conceptually

Generation happens in three stages, and you control each one separately:

1. **Content** — a *generator* returns `turns`: a list of `(station_index, text)`
   pairs. `station_index` is `0` or `1`, saying who sends that over.
2. **Voices** — a `stations` list of two `Station` objects. `stations[0]` renders
   every turn tagged `0`, `stations[1]` every turn tagged `1`. This is how the
   two ops get different speeds/pitches.
3. **Channel** — a `Channel` (usually built by `channel_for_difficulty`) adds
   noise, fading, and interference, then band-pass filters the result.

`synthesize_qso(turns, stations, ch)` runs all three and returns
`(audio_array, transcript_string)`.

---

## 3. Content generators

### `wordy_ragchew(rng, wordiness=0.7, corpus=None, corpus_tail=0)`

A full conversational ragchew — greetings, RST, name, QTH, rig, antenna, weather,
small talk. This is the main one for copy practice.

| Parameter | Type | Default | What it does |
|---|---|---|---|
| `rng` | `random.Random` | — | Seeded RNG; same seed → same QSO. Pass `random.Random(n)`. |
| `wordiness` | float `0`–`1` | `0.7` | Probability multiplier for *optional* overs and clauses. `0` = lean exchange, `1` = chatty with weather, occupation, extra small talk. |
| `corpus` | list/tuple of str, or `None` | `None` | Sentence pool for the in-QSO `BTW …` line and the tail. `None` = bundled default (Collins). `[]` = corpus off. Pass your own list to substitute. |
| `corpus_tail` | int | `0` | Append this many **full** plain-English corpus sentences after the sign-off, for straight text-copy practice. `0` = none. |

Returns `turns`. Full callsigns (`CALL DE CALL`) appear only on the opening
exchange and the sign-off; middle overs use light `BK` / `K` / `KN` handoffs.

### `ragchew_qso(rng)`

A short, fixed-structure ragchew (call, RST, name, QTH, rig, 73). No knobs beyond
the seed. Good for a quick, predictable contact.

### `contest_qso(rng, serial=None)`

A terse contest exchange (`5NN` + serial). `serial` lets you pin the serial
number; otherwise it's random.

```python
turns = ragchew_qso(random.Random(1))
turns = contest_qso(random.Random(1), serial=42)
```

---

## 4. `Station` — the per-operator voice

Two stations, one per side of the QSO. Every field has a sensible default, so
override only what you want.

| Field | Default | Meaning |
|---|---|---|
| `wpm` | `25.0` | Character speed (PARIS standard). |
| `farnsworth_wpm` | `None` | Effective speed — characters stay at `wpm` but spacing stretches to this slower rate. `None` = no Farnsworth. Set e.g. `18` to learn at 25 wpm character speed but 18 wpm overall. |
| `freq` | `600.0` | Sidetone pitch in Hz. |
| `amplitude` | `1.0` | Relative loudness (`0`–`1`). |
| `rise_ms` | `5.0` | Keying edge ramp; lower = harder/clickier keying, higher = softer. |
| `jitter` | `0.0` | Timing imperfection as a fraction of element length. `0` = machine-perfect; `0.02`–`0.05` = human-sounding fist. |

Give the two stations slightly different `freq` (e.g. 600 / 610) so they're
distinguishable by ear, and different `wpm` if you want a speed mismatch.

```python
stations = [
    Station(wpm=22, farnsworth_wpm=15, freq=600, jitter=0.03),  # a human-ish fist
    Station(wpm=28, freq=650, amplitude=0.85),                  # faster, quieter, higher
]
```

---

## 5. Band conditions

### The easy way: `channel_for_difficulty(level, **overrides)`

One knob, `0`–`10`, maps onto every impairment at once:

| Level | Conditions |
|---|---|
| 0–1 | Armchair copy: clean tone, faint hiss, no fading |
| 2–3 | Easy: mild noise, shallow slow QSB |
| 4–5 | Working conditions: noticeable noise + fading, light crackle |
| 6–7 | Rough: low SNR, deep QSB, QRN, a QRM station |
| 8–10 | Contest pileup hell |

Any individual `Channel` field can still be overridden by keyword — most
commonly the sample rate:

```python
ch = channel_for_difficulty(4)                 # default fs = 11025
ch = channel_for_difficulty(6, fs=22050)       # higher sample rate
ch = channel_for_difficulty(3, qrm=False)      # difficulty 3 but force QRM off
```

### The manual way: build a `Channel` directly

For full control, construct a `Channel`. Fields:

| Field | Default | Meaning |
|---|---|---|
| `fs` | `11025` | Sample rate (Hz). Use `write_wav` + higher `fs` for ML/training data. |
| `snr_db` | `10.0` | Signal-to-noise in `ref_bw` (Morse Runner convention). Lower = noisier. |
| `ref_bw` | `500.0` | Reference bandwidth for the SNR figure. |
| `rx_center` | `600.0` | Receiver filter center (Hz) — match your station pitch. |
| `rx_bw` | `400.0` | Receiver filter width (Hz). Narrower = more selective. |
| `qsb_bw` | `0.0` | Fading speed (Hz). `0` disables QSB; `~0.1` is typical slow fading. |
| `qsb_depth` | `0.6` | Fading depth, `0`–`1`. |
| `qrn` | `False` | Atmospheric static crashes on/off. |
| `qrn_density` | `0.003` | Background impulse probability per sample. |
| `qrn_burst_rate` | `0.08` | Static crashes per second. |
| `qrn_level` | `1.0` | Impulse amplitude scale. |
| `qrm` | `False` | Interfering stations on/off. |
| `qrm_activity` | `1.0` | Mean number of QRM stations per file. |
| `qrm_level` | `0.4` | Loudness of QRM stations. |

```python
from procg_qso import Channel
ch = Channel(fs=11025, snr_db=8, qsb_bw=0.1, qsb_depth=0.7, qrn=True)
```

---

## 6. Rendering and saving

### `synthesize_qso(turns, stations, ch, seed=None, turn_gap_s=(0.8, 2.0))`

| Parameter | Default | Meaning |
|---|---|---|
| `turns` | — | From a generator. |
| `stations` | — | Two-element list of `Station`. |
| `ch` | — | A `Channel`. |
| `seed` | `None` | Seeds the render-time randomness (gap lengths, noise, QSB, QRM/QRN). Pass the same seed you gave the generator for a fully reproducible file. |
| `turn_gap_s` | `(0.8, 2.0)` | Min/max silence (seconds) between overs, chosen at random per gap. |

Returns `(sig, transcript)`. `sig` is a float NumPy array normalized to ±0.9;
`transcript` is the ground-truth text with `[idx]` tags.

### Save to disk

```python
write_wav("practice.wav", sig, ch.fs)          # lossless; best for training data
write_mp3("practice.mp3", sig, ch.fs, kbps=64) # needs lame or ffmpeg installed

with open("practice.txt", "w") as f:           # save the answer key
    f.write(transcript)
```

`write_mp3` raises if no encoder is found — use `write_wav` if so.

---

## 7. Customizing the word pools and corpus from the notebook

The persona word lists live in editable text files under
`src/procg_qso/data/pools/` (`names.txt`, `rigs.txt`, `qths.txt`, …), and the
sentence corpora under `src/procg_qso/data/corpora/`. Edit any file, one entry
per line (`#` lines and blanks ignored), to change the variety.

**Important notebook caveat:** these files are read once and cached when the
module first imports, so editing a `.txt` mid-session has no effect until you
**restart the kernel** (Kernel → Restart) and re-run your imports. In a plain
`.py` script each run is fresh, so this only bites in notebooks.

Check what's loaded:

```python
from procg_qso import pools
pools.available()      # ['antennas', 'greets', 'jobs', 'names', 'rigs', ...]
pools.load("rigs")     # the current rig choices
```

---

## 8. Handy recipes

**Reproduce an exact file** — same seed everywhere:

```python
seed = 1234
turns = wordy_ragchew(random.Random(seed), wordiness=0.8, corpus_tail=2)
sig, truth = synthesize_qso(turns, stations, ch, seed=seed)
```

**Pure head-copy drill** — lean QSO, no corpus, perfect fists, clean band:

```python
turns = wordy_ragchew(random.Random(0), wordiness=0.3, corpus=[])
stations = [Station(wpm=25, farnsworth_wpm=20, freq=600),
            Station(wpm=25, farnsworth_wpm=20, freq=600)]
sig, _ = synthesize_qso(turns, stations, channel_for_difficulty(0))
Audio(sig, rate=11025)
```

**Plain-English copy** — short QSO with a long corpus tail:

```python
turns = wordy_ragchew(random.Random(5), wordiness=0.4, corpus_tail=8)
```

**Generate a batch** to disk:

```python
for i in range(10):
    t = wordy_ragchew(random.Random(i), wordiness=0.7, corpus_tail=2)
    s, truth = synthesize_qso(t, stations, channel_for_difficulty(3), seed=i)
    write_wav(f"practice_{i:02d}.wav", s, 11025)
    open(f"practice_{i:02d}.txt", "w").write(truth)
```

**Inspect content without rendering** — just look at the text:

```python
for idx, text in wordy_ragchew(random.Random(42), corpus_tail=3):
    print(f"[{idx}] {text}")
```
