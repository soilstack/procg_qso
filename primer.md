# procg_qso — A Primer

## What it is

`procg_qso` procedurally generates complete CW QSOs as audio files, with controllable sending speed, operator realism, and band conditions, plus a ground-truth transcript for every file. It exists so you can practice head copy against material you have never heard, under conditions you choose, without depending on band openings or other operators. It can also emit lossless, labeled audio/transcript pairs for training or evaluating a CW decoder.

The same machinery is usable three ways: as a command-line tool (`procg_qso qso ...`), as an importable library (`from procg_qso import ...`), or interactively in a Jupyter notebook with inline audio playback.

## How it works

The system is three independent layers. Each can be varied without touching the others, which is what makes it useful for training: you can hold two layers constant and isolate the third.

### Layer 1: Content

A QSO is generated as a list of turns, each a text string belonging to one of two stations. The `wordy_ragchew` generator creates a `Persona` for each side (callsign, name, QTH, rig, antenna, power, weather, age, years licensed, occupation) and assembles overs from clause pools. Each optional clause is gated by a probability scaled by the `wordiness` parameter, so no two QSOs have the same shape. The generator also models conversational mechanics: a consistent time-of-day greeting per QSO, varied abbreviations (TNX/TKS, K/KN/BK turnovers), an optional small-talk over, the dit-dit signoff, and repair exchanges — when the exchanged RST indicates weak copy, one station breaks in with "PSE RPT NAME" and gets the name repeated three times, just as on the air. `ragchew_qso` is the compact version (basics only, fits five minutes at slow speeds) and `contest_qso` produces 5NN-plus-serial exchanges.

Callsigns are built from weighted real prefix pools rather than random letters, because plausible callsign shapes (K3DS, JA1xxx, M8SK) are part of what your ear learns to anticipate.

### Layer 2: Keying

Text becomes a timing sequence using the PARIS standard: one dit is 1.2/WPM seconds, with the usual 1/3/3/7 ratios for element, intra-character, inter-character, and inter-word spacing. Farnsworth spacing uses the ARRL formula — characters are keyed at the character speed and the surplus time is distributed 3/19 into character gaps and 7/19 into word gaps — so `Station(wpm=25, farnsworth_wpm=15)` sounds like 25 WPM characters with 15 WPM thinking room. A per-element Gaussian `jitter` turns machine keying into a human fist. The keyed tone gets raised-cosine ramps of a few milliseconds on every edge; hard on/off keying produces clicks that make code artificially easy to copy and sound nothing like a real transmitter.

### Layer 3: Channel

This layer follows Morse Runner's DSP approach. Fading (QSB) is Rayleigh flat fading: a complex Gaussian process is low-pass filtered to a fraction of a hertz, and its envelope becomes a slowly varying gain — producing irregular, occasionally deep fades rather than periodic wobble. Static (QRN) is impulse noise in two forms, background crackle and dense short bursts, injected *before* the receiver bandpass so the filter ringing turns each impulse into a realistic crash. Interference (QRM) is generated as actual stations — random pitch inside the passband, 28–48 WPM, sending QRL?/CQ/QSY a few times and leaving. Broadband noise is added at an SNR calibrated to a 500 Hz reference bandwidth (the Morse Runner convention, so the numbers are comparable), and the whole mix passes through a 400 Hz Butterworth bandpass simulating the receiver.

All of this collapses into one knob: `channel_for_difficulty(0–10)` maps the level onto every impairment at once (0–1 armchair, 4–5 working conditions, 7+ rough), and any individual `Channel` field can still be overridden by keyword.

## Setting up a local environment

The library is a normal `pip`-installable package with a `src/` layout. The goal of the setup is an *editable* install (`pip install -e`), which links the package into your Python environment so that `import procg_qso` works from anywhere — any notebook, any directory — with no `PYTHONPATH` fiddling, and so that edits to the source take effect on the next kernel restart. Editing the source and using the library become the same install.

### With an existing conda environment (recommended)

Use whatever environment you already work in; there is no need to create a new one. From the cloned repository root (the directory containing `pyproject.toml`), with the environment active:

```
pip install -e .
```

That is the entire setup. `pip install -e` inside a conda environment is standard and fine. NumPy and SciPy install automatically if the environment lacks them.

Verify the link points at this clone rather than a stale copy elsewhere:

```
python -c "import procg_qso; print(procg_qso.__file__)"
```

The printed path should end in `...\procg_qso\src\procg_qso\__init__.py`. That single command is also the diagnostic to reach for if an import ever resolves to the wrong thing.

### A note on where pip installs it

If the conda environment's `site-packages` is not writeable (common when Anaconda lives under `C:\ProgramData`), pip prints "Defaulting to user installation" and installs into the per-user location instead. Imports still work, so notebook use is unaffected. Two consequences are worth knowing:

- The `procg_qso` **command-line tool** may land in a Scripts directory that is not on `PATH`, so the `procg_qso ...` command will not run from a terminal until that directory is added to `PATH`. This does not affect `import procg_qso`, so if you drive everything from notebooks it does not matter.
- The install becomes visible to any Python of that version on the machine, not just the one environment.

To install cleanly *into* the environment (which also puts the CLI on the activated-environment `PATH`), reinstall from an Anaconda Prompt opened **as Administrator**:

```
pip uninstall procg_qso
pip install -e .
```

This is optional polish; for using and editing the library from notebooks, the user-level install already does everything needed.

### Per-machine, per-environment

The editable link is specific to one environment on one machine. On a second computer (or a second conda environment), run `pip install -e .` once there too. After that, pulling code changes with git never requires reinstalling — the link already points at the source. Only a change to `pyproject.toml`'s dependencies warrants re-running the install.

## Using it from a Jupyter notebook

Keep notebooks in a `notebooks/` folder at the repository root so they are version-controlled alongside the code but never mistaken for package source. Install Jupyter into the same environment that holds the editable install (`pip install jupyterlab`), then `jupyter lab` from the repo root.

Because of the editable install, the import needs no path setup regardless of where the notebook file sits. Start each notebook with the autoreload header so edits to `core.py` appear without restarting the kernel, and use the `IPython.display.Audio` widget to hear results inline — a far tighter loop for dialing in difficulty than writing files and opening them:

```python
%load_ext autoreload
%autoreload 2

import random
from procg_qso import Station, channel_for_difficulty, wordy_ragchew, synthesize_qso
from IPython.display import Audio

ch = channel_for_difficulty(2)
st = [Station(wpm=25, farnsworth_wpm=18, freq=600),
      Station(wpm=22, freq=610, amplitude=0.9)]
audio, truth = synthesize_qso(wordy_ragchew(random.Random(1), 0.7), st, ch, seed=1)
print(truth)
Audio(audio, rate=ch.fs)
```

Keep notebook *output* out of git so diffs stay readable and the repo stays small: add `.ipynb_checkpoints/` to `.gitignore` and clear outputs before committing (JupyterLab: Edit → Clear All Outputs). Once there is more than a notebook or two, `pip install nbstripout && nbstripout --install` strips outputs automatically on commit.

## Using it from the command line

The CLI wraps the same library with two subcommands. `qso` makes one file; `grid` batch-generates a speed × difficulty matrix with a fresh random seed per file. `--minutes` searches seeds to hit a target duration.

```
# one easy ~5-minute QSO, 25 WPM characters at 15 WPM effective
procg_qso qso --wpm 25 --farnsworth 15 --difficulty 1 --minutes 5

# bracket your straight-speed copy threshold
procg_qso grid --wpms 13,13.5,14 --difficulties 0 --outdir bracket/

# contest practice under rough conditions
procg_qso qso --style contest --wpm 32 --difficulty 7
```

Every output file gets a matching `.txt` transcript. MP3 output needs `lame` or `ffmpeg` on `PATH`; without one, `--format mp3` falls back to WAV with a warning.

## Typical usage permutations

**Speed bracketing.** Hold the channel at zero (`channel_for_difficulty(0, snr_db=40)`) and vary only straight WPM in fine steps near your limit. Copy ability falls off sharply within 1–2 WPM of the threshold, so 13.0/13.5/14.0 locates it better than 12/15/18. Always use a fresh random seed per file — re-copying known content measures memory, not copy.

**Farnsworth ladder.** Once the floor is known, fix `wpm=25` and walk `farnsworth_wpm` upward from just below your straight-speed floor (e.g., 12 → 14 → 16 → 18 → 20). Characters keep their 25 WPM sound throughout, so speed gains transfer. The 22→25 endgame is where most people stall; budget extra repetitions there.

**Conditions progression.** With speed fixed at a comfortable level, climb `channel_for_difficulty` from 2 upward. To find out *which* impairment breaks your copy, introduce them singly via overrides: `channel_for_difficulty(2, qrn=True)` or `channel_for_difficulty(2, qsb_bw=0.1, qsb_depth=0.6)` isolates static crashes or deep fading against an otherwise easy channel.

**Contest practice.** Swap `wordy_ragchew` for `contest_qso` at high WPM and moderate-to-rough conditions. The fixed exchange format means you can run speeds well above your ragchew limit.

**Practice library.** Loop over a (speed × difficulty) grid — or use `procg_qso grid` — write MP3s (transparent at 64 kbps mono for a single tone; 32 kbps still fine), and load them onto a phone. Setting `Channel(fs=8000)` shrinks files further since nothing lives above ~1 kHz. Keep each file's `.txt` ground truth alongside for checking.

**Dataset generation.** The same grid loop, but written as WAV — lossless, no encoder delay — gives sample-accurate audio/transcript pairs for training or evaluating a CW decoder, with SNR, speed, fading, and interference as labeled, controlled variables.

## The one rule

Whatever the session, change one layer at a time. The system's value is that content difficulty, sending speed, and channel difficulty are fully decoupled — a property real off-air practice never gives you.
