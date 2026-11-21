"""Read explicitly tabulated glued beams from production PDF text."""
import re
from dataclasses import dataclass, asdict

BEAM_RE = re.compile(r"^\s*(\d+)\s+Glued\s+beam\s*/\s*līmsija\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?!\d)", re.IGNORECASE)

@dataclass(frozen=True)
class Beam:
    number: int
    width_mm: int
    height_mm: int
    length_mm: int
    count: int
    page: int

    @property
    def volume_m3(self):
        return self.width_mm * self.height_mm * self.length_mm * self.count / 1_000_000_000

    def to_dict(self):
        return {**asdict(self), "volume_m3": round(self.volume_m3, 6)}

def parse_beams(page_texts):
    """Only reads explicit table rows; does not infer geometry from lines."""
    beams = []
    for page_no, text in enumerate(page_texts, 1):
        if "Timber Element list" not in text or "Structural Frame" not in text:
            continue
        for line in text.splitlines():
            match = BEAM_RE.match(line)
            if match:
                no, width, height, length, count = map(int, match.groups())
                if min(width, height, length, count) > 0:
                    beams.append(Beam(no, width, height, length, count, page_no))
    return beams

def summarize(beams):
    return {"positions": len(beams), "pieces": sum(b.count for b in beams),
            "volume_m3": round(sum(b.volume_m3 for b in beams), 6)}
