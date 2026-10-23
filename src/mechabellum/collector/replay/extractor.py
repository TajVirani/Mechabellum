from pathlib import Path
from xml.etree import ElementTree

XML_START = b"<?xml"
BATTLE_RECORD_END = b"</BattleRecord>"
MAX_XML_BYTES = 64 * 1024 * 1024


def extract_battle_record(path: Path) -> ElementTree.Element:
    if not path.is_file():
        raise FileNotFoundError(f"Replay file not found: {path}")
    data = path.read_bytes()
    start = data.find(XML_START)
    if start < 0:
        raise ValueError("BattleRecord XML start marker not found in replay.")
    end = data.find(BATTLE_RECORD_END, start)
    if end < 0:
        raise ValueError("BattleRecord XML in replay is incomplete.")
    payload = data[start : end + len(BATTLE_RECORD_END)]
    if len(payload) > MAX_XML_BYTES:
        raise ValueError(f"Replay XML exceeds the safety limit of {MAX_XML_BYTES // 1024 // 1024} MiB.")
    if b"<!DOCTYPE" in payload.upper():
        raise ValueError("BattleRecord XML contains a disallowed DTD.")
    return ElementTree.fromstring(payload)
