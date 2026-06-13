# procg_qso

Procedural CW (Morse code) QSO generator with realistic band-condition
simulation. Generates complete, never-repeating QSOs as audio files with
ground-truth transcripts, for head-copy training and decoder datasets.

- PARIS-standard timing, ARRL Farnsworth spacing, per-element "fist" jitter,
  raised-cosine keying envelopes
- Channel model ported from Morse Runner: Rayleigh QSB, impulse QRN injected
  before the RX bandpass, scheduled QRM stations, SNR calibrated to a 500 Hz
  reference bandwidth
- One difficulty knob (0-10) or per-impairment overrides
- Ragchew (minimal or wordy, with repeat-request repair exchanges) and
  contest exchange generators; weighted real-prefix callsigns
- WAV or MP3 output (MP3 needs `lame` or `ffmpeg` on PATH)

## Install

    pip install -e .

## Quick start

    # one easy 5-minute QSO, 25 WPM characters at 15 WPM effective
    procg_qso qso --wpm 25 --farnsworth 15 --difficulty 1 --minutes 5

    # bracket your straight-speed copy threshold
    procg_qso grid --wpms 13,13.5,14 --difficulties 0 --outdir bracket/

    # contest practice under rough conditions
    procg_qso qso --style contest --wpm 32 --difficulty 7

Every output file gets a matching `.txt` transcript. See `docs/primer.md`
for the design and training-workflow guide.

## Library use

```python
from procg_qso import Station, channel_for_difficulty, wordy_ragchew, synthesize_qso, write_mp3
import random

ch = channel_for_difficulty(2)
st = [Station(wpm=25, farnsworth_wpm=18, freq=600),
      Station(wpm=22, freq=610, amplitude=0.9)]
turns = wordy_ragchew(random.Random(42), wordiness=0.7)
audio, transcript = synthesize_qso(turns, st, ch, seed=42)
write_mp3("qso.mp3", audio, ch.fs)
```

## Reproducibility

Same seed = same transcript and audio, within a minor version. Content-pool
or template changes bump the minor version (see CHANGELOG).

## Acknowledgements

Channel-simulation approach follows Alex Shovkoplyas VE3NEA's Morse Runner,
via the WebMorseRunner port by fritzsche.
