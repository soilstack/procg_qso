"""procg_qso — procedural CW QSO generator with band-condition simulation."""

from procg_qso.core import (
    Channel,
    Persona,
    Station,
    add_noise,
    add_qrm,
    add_qrn,
    apply_qsb,
    channel_for_difficulty,
    contest_qso,
    make_persona,
    qrm_messages,
    ragchew_qso,
    random_call,
    random_rst,
    render_station,
    rx_filter,
    synthesize_qso,
    wordy_ragchew,
    write_mp3,
    write_wav,
)

__version__ = "0.1.0"

__all__ = [
    "Channel", "Persona", "Station", "add_noise", "add_qrm", "add_qrn",
    "apply_qsb", "channel_for_difficulty", "contest_qso", "make_persona",
    "qrm_messages", "ragchew_qso", "random_call", "random_rst",
    "render_station", "rx_filter", "synthesize_qso", "wordy_ragchew",
    "write_mp3", "write_wav", "__version__",
]
