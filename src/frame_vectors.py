"""Vector PDF beam candidate recognition. Validate against engineering drawings."""
DEFAULT_GL_FILL = (0.84, 0.66, 0.34)

def detect_beams(page, drawing_scale=40, fill_rgb=DEFAULT_GL_FILL, tolerance=0.025):
    """Detect solid gold-filled rectangles; dimensions are inferred from drawing scale."""
    mm_per_pt = drawing_scale * 25.4 / 72
    results = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill is None or any(abs(a - b) > tolerance for a, b in zip(fill, fill_rgb)):
            continue
        rect = drawing["rect"]
        if rect.width <= 0 or rect.height <= 0:
            continue
        width = min(rect.width, rect.height) * mm_per_pt
        length = max(rect.width, rect.height) * mm_per_pt
        if not (30 <= width <= 250 and 100 <= length <= 11000):
            continue
        results.append({
            "width_mm": round(width), "length_mm": round(length),
            "orientation": "horizontal" if rect.width > rect.height else "vertical",
            "rect": [round(v, 2) for v in rect], "source": "PDF vector fill"
        })
    return results

def compare_to_schedule(detected, schedule, width_tolerance_mm=3, length_tolerance_mm=8):
    """Match each vector rectangle to at most one tabulated beam."""
    remaining = [beam for beam in schedule for _ in range(beam.count)]
    matched, unmatched = [], []
    for candidate in detected:
        choices = [
            (abs(candidate["width_mm"] - beam.width_mm) +
             abs(candidate["length_mm"] - beam.length_mm), i)
            for i, beam in enumerate(remaining)
            if abs(candidate["width_mm"] - beam.width_mm) <= width_tolerance_mm
            and abs(candidate["length_mm"] - beam.length_mm) <= length_tolerance_mm
        ]
        if choices:
            _, idx = min(choices)
            beam = remaining.pop(idx)
            matched.append({**candidate, "schedule_number": beam.number,
                            "height_mm": beam.height_mm})
        else:
            unmatched.append(candidate)
    return {
        "matched": matched,
        "unmatched_graphics": unmatched,
        "unmatched_schedule": [
            {"number": beam.number, "width_mm": beam.width_mm,
             "length_mm": beam.length_mm} for beam in remaining
        ],
    }
