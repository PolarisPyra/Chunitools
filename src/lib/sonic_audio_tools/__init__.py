"""Small Python port of the SonicAudioTools AWB/HCA export pieces."""

from src.lib.sonic_audio_tools.acb import retarget_acb_template
from src.lib.sonic_audio_tools.afs2 import Afs2Entry, build_afs2, extract_afs2_header, parse_afs2
from src.lib.sonic_audio_tools.hca import (
    HcaEncodeError,
    HcaInfo,
    encode_source_to_hca,
    hca_encoder_available,
    read_hca_info,
    read_wav_info,
)

__all__ = [
    "Afs2Entry",
    "HcaEncodeError",
    "HcaInfo",
    "build_afs2",
    "encode_source_to_hca",
    "extract_afs2_header",
    "hca_encoder_available",
    "parse_afs2",
    "read_hca_info",
    "read_wav_info",
    "retarget_acb_template",
]
