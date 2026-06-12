# Changelog

Seed reproducibility policy: identical seeds produce identical transcripts
and audio only within a minor version. Any change to content pools, clause
templates, or RNG call order is a minor-version bump.

## 0.1.0 - 2026-06-12
- Initial release: PARIS/Farnsworth keying with per-element jitter,
  raised-cosine envelopes, Morse Runner-style channel (Rayleigh QSB,
  pre-filter QRN impulses, scheduled QRM stations), calibrated SNR
  (500 Hz reference), single difficulty knob, minimal/wordy/contest
  QSO generators, WAV/MP3 output, CLI with qso and grid commands.
