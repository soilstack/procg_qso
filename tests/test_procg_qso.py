"""Tests that pin down the physics and reproducibility guarantees.

If a refactor breaks PARIS timing, the Farnsworth formula, SNR calibration,
or seed determinism, these fail.
"""

import random

import numpy as np
import pytest

from procg_qso.core import (MORSE, Channel, Station, add_noise, apply_qsb,
                        channel_for_difficulty, contest_qso, keying_elements,
                        ragchew_qso, synthesize_qso, wordy_ragchew)


# ------------------------------------------------------------------- timing
def test_dit_length_paris():
    st = Station(wpm=20)
    elems = list(keying_elements("E", st, random.Random(0)))
    assert len(elems) == 1
    down, dur = elems[0]
    assert down
    assert dur == pytest.approx(1.2 / 20)


def test_dah_is_three_dits():
    st = Station(wpm=25)
    elems = list(keying_elements("T", st, random.Random(0)))
    assert elems[0][1] == pytest.approx(3 * 1.2 / 25)


def test_word_space_is_seven_units():
    st = Station(wpm=20)
    elems = list(keying_elements("E E", st, random.Random(0)))
    gaps = [d for down, d in elems if not down]
    assert gaps[0] == pytest.approx(7 * 1.2 / 20)


def test_farnsworth_stretches_gaps_not_characters():
    fast = Station(wpm=25)
    farns = Station(wpm=25, farnsworth_wpm=15)
    e_fast = list(keying_elements("AB", fast, random.Random(0)))
    e_farn = list(keying_elements("AB", farns, random.Random(0)))
    # key-down element durations identical (character speed unchanged)
    assert ([d for k, d in e_fast if k]
            == pytest.approx([d for k, d in e_farn if k]))
    # inter-character gap longer under Farnsworth
    gap_fast = max(d for k, d in e_fast if not k)
    gap_farn = max(d for k, d in e_farn if not k)
    assert gap_farn > gap_fast


def test_farnsworth_noop_when_not_slower():
    a = Station(wpm=20)
    b = Station(wpm=20, farnsworth_wpm=25)
    assert (list(keying_elements("CQ", a, random.Random(0)))
            == list(keying_elements("CQ", b, random.Random(0))))


# ------------------------------------------------------------------ channel
def test_snr_calibration_within_tolerance():
    fs, f0 = 11025, 600
    t = np.arange(fs * 20) / fs
    sig = np.sin(2 * np.pi * f0 * t)
    ch = Channel(fs=fs, snr_db=10.0)
    noisy = add_noise(sig, ch, np.random.default_rng(0))
    noise = noisy - sig
    p_sig = np.mean(sig ** 2)
    p_noise_ref = np.mean(noise ** 2) * ch.ref_bw / (fs / 2.0)
    snr_est = 10 * np.log10(p_sig / p_noise_ref)
    assert snr_est == pytest.approx(10.0, abs=0.5)


def test_qsb_unit_mean_gain():
    rng_np = np.random.default_rng(1)
    sig = np.ones(11025 * 120)
    faded = apply_qsb(sig, 11025, 0.1, 1.0, rng_np)
    assert np.mean(faded) == pytest.approx(1.0, abs=0.1)
    assert np.min(faded) < 0.3          # deep fades exist
    assert np.max(faded) > 1.4


def test_qsb_disabled_passthrough():
    sig = np.ones(1000)
    out = apply_qsb(sig, 11025, 0.0, 0.6, np.random.default_rng(0))
    assert np.array_equal(sig, out)


def test_difficulty_zero_disables_impairments():
    ch = channel_for_difficulty(0)
    assert ch.qsb_bw == 0 and not ch.qrn and not ch.qrm
    assert ch.snr_db >= 25


def test_difficulty_override():
    ch = channel_for_difficulty(0, snr_db=40, qrn=True)
    assert ch.snr_db == 40 and ch.qrn


# ------------------------------------------------------------------ content
@pytest.mark.parametrize("gen", [ragchew_qso, contest_qso,
                                 lambda r: wordy_ragchew(r, 0.9)])
@pytest.mark.parametrize("seed", range(5))
def test_all_generated_chars_renderable(gen, seed):
    for _, text in gen(random.Random(seed)):
        for ch in text.upper():
            assert ch == " " or ch in MORSE, f"unrenderable char {ch!r}"


def test_transcript_deterministic_for_seed():
    a = wordy_ragchew(random.Random(123), 0.7)
    b = wordy_ragchew(random.Random(123), 0.7)
    assert a == b


def test_audio_deterministic_for_seed():
    st = [Station(wpm=25), Station(wpm=22, freq=610)]
    ch = channel_for_difficulty(3)
    turns = ragchew_qso(random.Random(5))
    a1, t1 = synthesize_qso(turns, st, ch, seed=5)
    a2, t2 = synthesize_qso(turns, st, ch, seed=5)
    assert t1 == t2
    assert np.array_equal(a1, a2)


def test_audio_normalized():
    st = [Station(wpm=30), Station(wpm=30, freq=610)]
    turns = contest_qso(random.Random(1))
    audio, _ = synthesize_qso(turns, st, channel_for_difficulty(5), seed=1)
    assert np.max(np.abs(audio)) == pytest.approx(0.9, abs=1e-6)
