"""procg_qso.core — procedural CW QSO generator with channel simulation.

Layers:
  1. QSO text generation  (callsigns, exchange templates, contest mode)
  2. Keying               (PARIS timing, Farnsworth, jitter, raised-cosine edges)
  3. Channel              (AWGN at calibrated SNR, QSB, QRM, RX bandpass)

Requires: numpy, scipy. Output: 16-bit WAV + ground-truth transcript.
"""

import random
import wave
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import butter, sosfilt

# ---------------------------------------------------------------- Morse table
MORSE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',  'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',   'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '/': '-..-.', '?': '..--..', '.': '.-.-.-', ',': '--..--',
    '=': '-...-',   # BT (break)
    '+': '.-.-.',   # AR (end of message)
    '*': '...-.-',  # SK (end of contact) — use '*' in templates
}

# ------------------------------------------------------------ station/channel
@dataclass
class Station:
    wpm: float = 25.0
    farnsworth_wpm: float | None = None   # effective speed; None = no Farnsworth
    freq: float = 600.0                   # sidetone Hz
    amplitude: float = 1.0
    rise_ms: float = 5.0                  # keying edge ramp
    jitter: float = 0.0                   # stddev as fraction of element length

@dataclass
class Channel:
    fs: int = 11025
    snr_db: float = 10.0          # SNR in ref_bw (Morse Runner convention)
    ref_bw: float = 500.0
    rx_center: float = 600.0      # RX filter center
    rx_bw: float = 400.0          # RX filter width
    # QSB — Rayleigh flat fading (filtered complex Gaussian envelope)
    qsb_bw: float = 0.0           # fading process bandwidth, Hz; 0 disables (~0.1 typical)
    qsb_depth: float = 0.6        # 0..1 mix of faded vs dry
    # QRN — impulse noise injected BEFORE the RX bandpass (filter ringing -> crackle)
    qrn: bool = False
    qrn_density: float = 0.003    # per-sample background impulse probability
    qrn_burst_rate: float = 0.08  # static crashes per second (Poisson)
    qrn_level: float = 1.0        # impulse amplitude scale
    # QRM — interfering stations (QRL?/CQ/QSY) with own pitch, speed, fading
    qrm: bool = False
    qrm_activity: float = 1.0     # mean number of QRM stations per file (Poisson, min 1)
    qrm_level: float = 0.4

# ------------------------------------------------------------------- timing
def _unit_times(st: Station):
    """Return (dit_sec, interchar_sec, interword_sec) honoring Farnsworth."""
    c = st.wpm
    dit = 1.2 / c
    if st.farnsworth_wpm and st.farnsworth_wpm < c:
        s = st.farnsworth_wpm
        ta = (60.0 * c - 37.2 * s) / (s * c)   # ARRL Farnsworth total delay
        return dit, 3.0 * ta / 19.0, 7.0 * ta / 19.0
    return dit, 3.0 * dit, 7.0 * dit

def keying_elements(text: str, st: Station, rng: random.Random):
    """Yield (is_key_down, duration_seconds) for the whole message."""
    dit, ichar, iword = _unit_times(st)

    def j(d):  # per-element timing jitter ("fist")
        return d * max(0.3, 1.0 + rng.gauss(0.0, st.jitter)) if st.jitter else d

    words = text.upper().split()
    for wi, word in enumerate(words):
        if wi:
            yield (False, iword)
        chars = [ch for ch in word if ch in MORSE]
        for ci, ch in enumerate(chars):
            if ci:
                yield (False, ichar)
            code = MORSE[ch]
            for ei, sym in enumerate(code):
                if ei:
                    yield (False, j(dit))
                yield (True, j(3 * dit if sym == '-' else dit))

# ------------------------------------------------------------------ rendering
def render_station(text: str, st: Station, fs: int, rng: random.Random) -> np.ndarray:
    """Render one station's keyed tone (no noise)."""
    env_parts = []
    ramp = max(1, int(st.rise_ms / 1000.0 * fs))
    rise = 0.5 * (1 - np.cos(np.pi * np.arange(ramp) / ramp))   # raised cosine
    for down, dur in keying_elements(text, st, rng):
        n = max(1, int(round(dur * fs)))
        seg = np.ones(n) if down else np.zeros(n)
        if down and n > 2 * ramp:
            seg[:ramp] *= rise
            seg[-ramp:] *= rise[::-1]
        env_parts.append(seg)
    env = np.concatenate(env_parts) if env_parts else np.zeros(1)
    t = np.arange(env.size) / fs
    return st.amplitude * env * np.sin(2 * np.pi * st.freq * t)

def _pad_to(x: np.ndarray, n: int) -> np.ndarray:
    return np.pad(x, (0, n - x.size)) if x.size < n else x[:n]

def apply_qsb(sig: np.ndarray, fs: int, bw_hz: float, depth: float,
              rng_np: np.random.Generator) -> np.ndarray:
    """Rayleigh flat fading (Morse Runner's QSB model).

    Low-pass-filter a complex Gaussian process, take its envelope, use it
    as a slowly-varying gain mixed with the dry signal. Irregular fades,
    unlike a sinusoid.
    """
    if bw_hz <= 0 or depth <= 0:
        return sig
    block = max(1, int(fs * 0.02))                 # gain updates every ~20 ms
    blk_rate = fs / block
    nblk = sig.size // block + 2
    warm = int(4 * blk_rate / bw_hz)               # discard filter settling
    g = (rng_np.normal(size=nblk + warm)
         + 1j * rng_np.normal(size=nblk + warm))
    sos = butter(3, min(0.45 * blk_rate, bw_hz), btype='low',
                 fs=blk_rate, output='sos')
    env = np.abs(sosfilt(sos, g))[warm:]
    env /= np.mean(env) + 1e-12                    # mean gain ~= 1
    gain = env * depth + (1.0 - depth)
    return sig * np.interp(np.arange(sig.size),
                           np.arange(nblk) * block, gain)

def add_qrn(sig: np.ndarray, ch: Channel, rng: random.Random,
            rng_np: np.random.Generator) -> np.ndarray:
    """Impulse noise. Must be added BEFORE rx_filter(): the bandpass
    ringing on each impulse is what makes crackle/static sound real."""
    out = sig.copy()
    peak = np.max(np.abs(sig)) + 1e-12
    # background crackle: sparse single-sample impulses
    mask = rng_np.random(out.size) < ch.qrn_density
    out[mask] += 10 * ch.qrn_level * peak * rng_np.uniform(-1, 1, mask.sum())
    # static crashes: short dense bursts of large impulses
    for _ in range(rng_np.poisson(ch.qrn_burst_rate * out.size / ch.fs)):
        start = rng.randrange(out.size)
        seg = out[start:start + int(ch.fs * rng.uniform(0.05, 0.8))]
        m = rng_np.random(seg.size) < 0.02
        seg[m] += 25 * ch.qrn_level * peak * rng_np.uniform(-1, 1, m.sum())
    return out

def add_noise(sig: np.ndarray, ch: Channel, rng_np: np.random.Generator):
    """AWGN with SNR defined in ch.ref_bw Hz of bandwidth."""
    keyed = sig[np.abs(sig) > 1e-6]
    p_sig = np.mean(keyed ** 2) if keyed.size else 1e-12
    # noise power that falls inside ref_bw = sigma^2 * ref_bw / (fs/2)
    p_noise_ref = p_sig / (10 ** (ch.snr_db / 10.0))
    sigma = np.sqrt(p_noise_ref * (ch.fs / 2.0) / ch.ref_bw)
    return sig + rng_np.normal(0.0, sigma, sig.size)

def rx_filter(sig: np.ndarray, ch: Channel) -> np.ndarray:
    lo = max(50.0, ch.rx_center - ch.rx_bw / 2)
    hi = min(ch.fs / 2 - 50.0, ch.rx_center + ch.rx_bw / 2)
    sos = butter(4, [lo, hi], btype='bandpass', fs=ch.fs, output='sos')
    return sosfilt(sos, sig)

# ------------------------------------------------------------- QSO generation
PREFIXES = (['W', 'K', 'N'] * 5 + ['KA', 'KB', 'KD', 'KE', 'WA', 'WB', 'AA',
             'AB', 'AC', 'VE', 'VA', 'JA', 'JE', 'JH', 'DL', 'G', 'M', 'F',
             'EA', 'I', 'VK', 'ZL', 'PY', 'OH', 'SM', 'OK', 'SP', '9V'])
NAMES = ['JOHN', 'MIKE', 'DAVE', 'BOB', 'JIM', 'TOM', 'BILL', 'RON', 'KEN',
         'STEVE', 'AL', 'ED', 'JOE', 'RICK', 'DAN', 'ANN', 'SUE', 'KAZU']
QTHS = ['OHIO', 'TEXAS', 'FLA', 'CALIF', 'PA', 'NY', 'TOKYO', 'OSAKA',
        'LONDON', 'BERLIN', 'MADRID', 'SYDNEY', 'TORONTO', 'SINGAPORE']
RIGS = ['FT891', 'IC7300', 'K3', 'QMX', 'FLEX 8400', 'KX2', 'TS590']

def random_call(rng: random.Random) -> str:
    p = rng.choice(PREFIXES)
    suffix = ''.join(rng.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                                 k=rng.choice([1, 2, 2, 3, 3])))
    return f"{p}{rng.randint(0, 9)}{suffix}"

def random_rst(rng: random.Random) -> str:
    return f"{rng.choice('345')}{rng.choice('456789')}9"

def ragchew_qso(rng: random.Random):
    """Return list of (station_index, text) turns. Station 0 = CQer."""
    c1, c2 = random_call(rng), random_call(rng)
    n1, n2 = rng.choice(NAMES), rng.choice(NAMES)
    q1, q2 = rng.choice(QTHS), rng.choice(QTHS)
    r12, r21 = random_rst(rng), random_rst(rng)
    rig = rng.choice(RIGS)
    return [
        (0, f"CQ CQ CQ DE {c1} {c1} {c1} K"),
        (1, f"{c1} DE {c2} {c2} K"),
        (0, f"{c2} DE {c1} = GA TNX FER CALL = UR RST {r12} {r12} = "
            f"NAME {n1} {n1} = QTH {q1} {q1} = HW? {c2} DE {c1} K"),
        (1, f"{c1} DE {c2} = R R TNX {n1} = UR RST {r21} {r21} = "
            f"NAME {n2} {n2} = QTH {q2} {q2} = RIG {rig} = {c1} DE {c2} K"),
        (0, f"{c2} DE {c1} = FB {n2} TNX QSO = 73 ES CU AGN = "
            f"{c2} DE {c1} *"),
        (1, f"{c1} DE {c2} = 73 {n1} = {c1} DE {c2} *"),
    ]

def contest_qso(rng: random.Random, serial: int | None = None):
    c1, c2 = random_call(rng), random_call(rng)
    s = serial if serial is not None else rng.randint(1, 1500)
    return [
        (0, f"CQ TEST {c1} {c1}"),
        (1, f"{c2}"),
        (0, f"{c2} 5NN {s}"),
        (1, f"5NN {rng.randint(1, 1500)}"),
        (0, f"TU {c1}"),
    ]

# ------------------------------------------ wordier ragchews (variable depth)
ANTENNAS = ['DIPOLE UP 10M', 'EFHW', 'VERTICAL', 'HEXBEAM AT 12M', 'G5RV',
            'OCF DIPOLE', '3 EL YAGI', 'RANDOM WIRE ES TUNER',
            'MAG LOOP ON BALCONY', 'INV VEE']
POWERS = ['5W', '10W', '50W', '100W', 'QRP 5W']
WEATHERS = ['SUNNY', 'CLOUDY', 'RAINING', 'OVERCAST', 'CLR ES COLD',
            'HOT ES HUMID', 'SNOWING', 'WINDY', 'FOGGY']
JOBS = ['RETIRED', 'ENGINEER', 'TEACHER', 'PROGRAMMER', 'FARMER', 'STUDENT',
        'ELECTRICIAN', 'PILOT']
GREETS = ['GM', 'GA', 'GE']
THANKS = ['TNX', 'TKS', 'MNI TNX']
MISC_COMMENTS = ['CONDX FB TDY', 'BAND UP ES DOWN WID QSB', 'UR SIGS SOLID HR',
                 'SUM QRN FROM STORMS', 'FB SIG INTO {QTH}',
                 'DID FB POTA OUTING LAST WK HI HI', 'NICE FIST OM']

@dataclass
class Persona:
    call: str
    name: str
    qth: str
    rig: str
    ant: str
    pwr: str
    wx: str
    temp: int
    age: int
    yrs: int
    job: str

def make_persona(rng: random.Random) -> Persona:
    return Persona(random_call(rng), rng.choice(NAMES), rng.choice(QTHS),
                   rng.choice(RIGS), rng.choice(ANTENNAS), rng.choice(POWERS),
                   rng.choice(WEATHERS), rng.randint(28, 95),
                   rng.randint(22, 81), rng.randint(1, 55), rng.choice(JOBS))

def wordy_ragchew(rng: random.Random, wordiness: float = 0.7):
    """Variable-depth ragchew built from probability-gated clause pools.

    wordiness in [0,1] controls optional clauses (WX, power, age, job,
    misc small talk), extra overs, and repair exchanges. ~0.3 approximates
    a quick exchange; ~0.9 a long-winded one.
    """
    a, b = make_persona(rng), make_persona(rng)
    greet = rng.choice(GREETS)               # consistent time-of-day per QSO
    r_to_b, r_to_a = random_rst(rng), random_rst(rng)
    p = lambda x=1.0: rng.random() < wordiness * x
    turns = []

    def over(frm, to, sidx, parts, sig=None):
        parts = [s for s in parts if s]
        sig = sig or rng.choice(['K', 'K', 'KN', 'BK'])
        turns.append((sidx, f"{to.call} DE {frm.call} = "
                            + " = ".join(parts)
                            + f" = {to.call} DE {frm.call} {sig}"))

    turns.append((0, f"CQ CQ CQ DE {a.call} {a.call} {a.call} K"))
    turns.append((1, f"{a.call} DE {b.call} {b.call} K"))

    # --- over 1: A sends basics
    over(a, b, 0, [
        f"{greet} ES {rng.choice(THANKS)} FER CALL",
        f"UR RST {r_to_b} {r_to_b}",
        f"NAME {a.name} {a.name}",
        f"QTH {a.qth} {a.qth}",
        f"WX HR {a.wx} TEMP {a.temp}F" if p(0.6) else None,
        "HW CPY?"])

    # --- repair exchange when B's copy of A is weak
    if int(r_to_a[1]) <= 4 and p(0.9):
        turns.append((1, "SRI OM QSB QSB = PSE RPT NAME = BK"))
        turns.append((0, f"BK R R NAME {a.name} {a.name} {a.name} = BK"))

    # --- over 1: B replies with basics
    over(b, a, 1, [
        f"R R {greet} {a.name} ES {rng.choice(THANKS)} FER RPRT",
        f"UR RST {r_to_a} {r_to_a}",
        f"NAME {b.name} {b.name}",
        f"QTH {b.qth} {b.qth}",
        f"WX {b.wx} ES TEMP {b.temp}F" if p(0.6) else None])

    # --- over 2: station details
    over(a, b, 0, [
        f"R FB {b.name} SOLID CPY",
        f"RIG HR IS {a.rig}" + (f" PWR {a.pwr}" if p(0.7) else ""),
        f"ANT IS {a.ant}",
        f"BEEN LICENSED {a.yrs} YRS" if p(0.4) else None,
        "HW?"])
    over(b, a, 1, [
        f"R FB CPY {a.name}",
        f"FB ON THE {a.rig}" if p(0.5) else None,
        f"RIG HR {b.rig} ES ANT {b.ant}",
        f"PWR {b.pwr}" if p(0.6) else None,
        f"AGE {b.age} ES LICENSED {b.yrs} YRS" if p(0.4) else None,
        f"OCCUPATION HR {b.job}" if p(0.4) else None])

    # --- optional small-talk over
    if p(0.5):
        cm = rng.choice(MISC_COMMENTS).replace('{QTH}', b.qth)
        over(a, b, 0, [cm,
                       f"WX GETTING {rng.choice(['COLD', 'WARM'])} HR"
                       if p(0.4) else None])
        over(b, a, 1, [f"R R HI HI" if 'HI HI' in cm else "R R FB",
                       rng.choice(MISC_COMMENTS).replace('{QTH}', a.qth)
                       if p(0.4) else None])

    # --- closings
    over(a, b, 0, [
        f"{rng.choice(THANKS)} FER FB QSO {b.name}",
        "73 ES GL",
        rng.choice(['HPE CUL', 'CU AGN', 'BCNU'])], sig='*')
    turns.append((1, f"{a.call} DE {b.call} = R 73 {a.name} ES TNX QSO = "
                     f"{rng.choice(['BCNU', 'CUL', 'GL ES GD DX'])} = "
                     f"{a.call} DE {b.call} *"))
    if p(0.8):                                  # dit-dit signoff
        turns.append((0, "E E"))
        turns.append((1, "E E"))
    return turns

def qrm_messages(call: str):
    return [
        "QRL?",
        f"QRL? DE {call}",
        f"CQ CQ CQ DE {call} {call} {call} PSE K",
        "QSY QSY",
    ]

def add_qrm(sig: np.ndarray, ch: Channel, rng: random.Random,
            rng_np: np.random.Generator) -> np.ndarray:
    """Interfering stations a la Morse Runner's QrmStation: random pitch
    near the passband, fast fists, 1-4 transmissions each, then gone."""
    out = sig.copy()
    n = max(1, rng_np.poisson(ch.qrm_activity))
    for _ in range(n):
        call = random_call(rng)
        pitch = ch.rx_center + max(-0.45 * ch.rx_bw,
                                   min(0.45 * ch.rx_bw, rng.gauss(0, 150)))
        st = Station(wpm=rng.uniform(28, 48), freq=pitch,
                     amplitude=ch.qrm_level * rng.uniform(0.5, 1.5),
                     jitter=0.04, rise_ms=rng.uniform(3, 6))
        parts = []
        for _ in range(rng.randint(1, 4)):       # "patience"
            parts.append(render_station(rng.choice(qrm_messages(call)),
                                        st, ch.fs, rng))
            parts.append(np.zeros(int(rng.uniform(2, 6) * ch.fs)))
        track = apply_qsb(np.concatenate(parts), ch.fs,
                          max(ch.qsb_bw, 0.05), 0.5, rng_np)
        start = rng.randrange(max(1, out.size - track.size // 2))
        end = min(out.size, start + track.size)
        out[start:end] += track[:end - start]
    return out

# ----------------------------------------------------------------- assembly
def synthesize_qso(turns, stations, ch: Channel, seed: int | None = None,
                   turn_gap_s=(0.8, 2.0)):
    """Render a full QSO to a float array + transcript string."""
    rng = random.Random(seed)
    rng_np = np.random.default_rng(seed)
    pieces, transcript = [], []
    for idx, text in turns:
        st = stations[idx]
        pieces.append(render_station(text, st, ch.fs, rng))
        pieces.append(np.zeros(int(rng.uniform(*turn_gap_s) * ch.fs)))
        transcript.append(f"[{idx}] {text}")
    sig = np.concatenate(pieces)
    sig = apply_qsb(sig, ch.fs, ch.qsb_bw, ch.qsb_depth, rng_np)
    if ch.qrm:
        sig = add_qrm(sig, ch, rng, rng_np)
    if ch.qrn:
        sig = add_qrn(sig, ch, rng, rng_np)      # pre-filter, on purpose
    sig = add_noise(sig, ch, rng_np)
    sig = rx_filter(sig, ch)
    sig = 0.9 * sig / np.max(np.abs(sig))           # normalize w/ headroom
    return sig, "\n".join(transcript)

def write_wav(path: str, sig: np.ndarray, fs: int):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())

def write_mp3(path: str, sig: np.ndarray, fs: int, kbps: int = 64):
    """Encode via lame (or ffmpeg). 64 kbps mono is transparent for CW.
    Use write_wav instead for ML training data / sample-accurate timing."""
    import shutil, subprocess, tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        write_wav(tmp.name, sig, fs)
    try:
        if shutil.which('lame'):
            cmd = ['lame', '--quiet', '-m', 'm', '-b', str(kbps),
                   tmp.name, path]
        elif shutil.which('ffmpeg'):
            cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp.name,
                   '-ac', '1', '-b:a', f'{kbps}k', path]
        else:
            raise RuntimeError("no MP3 encoder found (install lame or ffmpeg)")
        subprocess.run(cmd, check=True)
    finally:
        os.unlink(tmp.name)

def channel_for_difficulty(level: float, **overrides) -> Channel:
    """Map a single difficulty knob (0-10) onto all channel impairments.

    ~0-1: armchair copy. clean tone, faint hiss, no fading
    ~2-3: easy. mild noise, shallow slow QSB
    ~4-5: working conditions. noticeable noise + fading, light crackle
    ~6-7: rough. low SNR, deep QSB, QRN, a QRM station
    ~8-10: contest pileup hell
    Any Channel field can still be overridden by keyword.
    """
    lv = max(0.0, min(10.0, level))
    params = dict(
        snr_db=30.0 - 3.0 * lv,
        qsb_bw=0.0 if lv < 1.5 else 0.04 + 0.012 * lv,
        qsb_depth=min(0.85, 0.09 * lv),
        qrn=lv >= 4.5,
        qrn_density=0.0008 * max(0.0, lv - 4.0),
        qrn_burst_rate=0.02 * max(0.0, lv - 4.0),
        qrm=lv >= 6.0,
        qrm_activity=max(0.0, lv - 5.0),
    )
    params.update(overrides)
    return Channel(**params)
