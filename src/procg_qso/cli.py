"""procg_qso CLI.

    procg_qso qso  --wpm 25 --farnsworth 15 --difficulty 2 --minutes 5
    procg_qso grid --wpms 13,13.5,14 --difficulties 0,2 --outdir practice/
"""

import argparse
import os
import random
import sys
from dataclasses import replace

from procg_qso.core import (Channel, Station, channel_for_difficulty,
                        contest_qso, keying_elements, ragchew_qso,
                        synthesize_qso, wordy_ragchew, write_mp3, write_wav)

STYLES = {"ragchew": ragchew_qso, "wordy": None, "contest": contest_qso}


def estimate_duration(turns, stations, turn_gap_s=(0.8, 2.0)) -> float:
    """Cheap duration estimate (no audio render) for seed searching."""
    rng = random.Random(0)
    total = 0.0
    for idx, text in turns:
        st = replace(stations[idx], jitter=0.0)
        total += sum(d for _, d in keying_elements(text, st, rng))
        total += sum(turn_gap_s) / 2.0
    return total


def make_turns(style: str, seed: int, wordiness: float):
    rng = random.Random(seed)
    if style == "wordy":
        return wordy_ragchew(rng, wordiness=wordiness)
    return STYLES[style](rng)


def find_seed_for_minutes(style, wordiness, stations, minutes, seed0,
                          tries=200, tol_s=10.0):
    """Search seeds for a QSO whose estimated length is near the target."""
    target = minutes * 60.0
    best = None
    for i in range(tries):
        seed = seed0 + i
        turns = make_turns(style, seed, wordiness)
        err = abs(estimate_duration(turns, stations) - target)
        if best is None or err < best[1]:
            best = (seed, err, turns)
        if err < tol_s:
            break
    return best[0], best[2], best[1]


def build_stations(args) -> list:
    fw = args.farnsworth if args.farnsworth else None
    wpm2 = args.wpm2 if args.wpm2 else args.wpm
    return [
        Station(wpm=args.wpm, farnsworth_wpm=fw, freq=args.pitch,
                jitter=args.jitter),
        Station(wpm=wpm2, farnsworth_wpm=fw, freq=args.pitch + 10,
                amplitude=0.9, jitter=args.jitter),
    ]


def emit(audio, truth, ch, path_base, fmt):
    os.makedirs(os.path.dirname(path_base) or ".", exist_ok=True)
    if fmt == "mp3":
        try:
            write_mp3(path_base + ".mp3", audio, ch.fs)
            out = path_base + ".mp3"
        except RuntimeError as e:
            print(f"({e} -- writing WAV instead)", file=sys.stderr)
            write_wav(path_base + ".wav", audio, ch.fs)
            out = path_base + ".wav"
    else:
        write_wav(path_base + ".wav", audio, ch.fs)
        out = path_base + ".wav"
    with open(path_base + ".txt", "w") as f:
        f.write(truth)
    print(f"{out}  ({audio.size / ch.fs:.1f} s)")


def cmd_qso(args):
    stations = build_stations(args)
    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    if args.minutes:
        seed, turns, err = find_seed_for_minutes(
            args.style, args.wordiness, stations, args.minutes, seed)
        if err > 30:
            print(f"warning: closest fit is {err:.0f} s off target; "
                  f"adjust --wordiness or --style", file=sys.stderr)
    else:
        turns = make_turns(args.style, seed, args.wordiness)
    ch = channel_for_difficulty(args.difficulty, fs=args.fs)
    audio, truth = synthesize_qso(turns, stations, ch, seed=seed)
    name = args.output or (f"qso_{args.style}_w{args.wpm:g}"
                           + (f"f{args.farnsworth:g}" if args.farnsworth else "")
                           + f"_d{args.difficulty:g}_s{seed}")
    emit(audio, truth, ch, name, args.format)


def cmd_grid(args):
    wpms = [float(x) for x in args.wpms.split(",")]
    diffs = [float(x) for x in args.difficulties.split(",")]
    for w in wpms:
        for d in diffs:
            sub = argparse.Namespace(**vars(args))
            sub.wpm, sub.difficulty = w, d
            sub.seed = random.randrange(1 << 30)   # fresh content per file
            sub.output = os.path.join(
                args.outdir, f"qso_w{w:g}"
                + (f"f{args.farnsworth:g}" if args.farnsworth else "")
                + f"_d{d:g}")
            cmd_qso(sub)


def main():
    p = argparse.ArgumentParser(prog="procg_qso",
                                description="Procedural CW QSO generator")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--wpm", type=float, default=20)
        sp.add_argument("--wpm2", type=float, default=0,
                        help="second station speed (default: same as --wpm)")
        sp.add_argument("--farnsworth", type=float, default=0,
                        help="effective speed; characters stay at --wpm")
        sp.add_argument("--difficulty", type=float, default=2,
                        help="band conditions 0-10 (0 = dead quiet)")
        sp.add_argument("--style", choices=list(STYLES), default="wordy")
        sp.add_argument("--wordiness", type=float, default=0.7)
        sp.add_argument("--minutes", type=float, default=0,
                        help="target length; searches seeds to fit")
        sp.add_argument("--pitch", type=float, default=600)
        sp.add_argument("--jitter", type=float, default=0.02)
        sp.add_argument("--fs", type=int, default=11025)
        sp.add_argument("--format", choices=["mp3", "wav"], default="mp3")
        sp.add_argument("--seed", type=int, default=None)

    q = sub.add_parser("qso", help="generate one QSO")
    common(q)
    q.add_argument("-o", "--output", default=None,
                   help="output path base (no extension)")
    q.set_defaults(func=cmd_qso)

    g = sub.add_parser("grid", help="batch generate a speed x difficulty grid")
    common(g)
    g.add_argument("--wpms", required=True, help="e.g. 13,13.5,14")
    g.add_argument("--difficulties", default="0", help="e.g. 0,2,4")
    g.add_argument("--outdir", default="procg_qso_out")
    g.set_defaults(func=cmd_grid)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
