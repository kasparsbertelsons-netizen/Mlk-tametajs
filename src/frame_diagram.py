"""Mērogota grīdas rāmja shēma (SVG) no `ModuleResult` ģeometrijas (Issue #10).

Shēma tiek zīmēta TIEŠI no aprēķina datiem (`result.members`, `result.gaps`, `result.reinforcements`), nevis kā
dekoratīvs aptuvens zīmējums: katram elementam ir `data-*` atribūti ar tā sākumu/beigām/asi (mm), un viena un tā
pati mērogs (px uz mm) tiek lietots visām sijām. Bez ārējiem servisiem un resursiem (tikai inline SVG).

Orientācija telefonam: garais virziens L ir VERTIKĀLS (uz leju), W — horizontāls; shēma ir šaura un augsta, un
tiek skatīta ritinot. Ass = sijas centra koordināta mm no moduļa ārējā gala (shēmā augšā).
"""
import textwrap
from html import escape

from src.reinforcement import CONVENTION_NOTE, KIND_ADD, KIND_END, KIND_REGULAR, KIND_REPLACE, format_axis

MAX_SCALE_PX_PER_MM = 0.125
MAX_HEIGHT_PX = 1500.0
MAX_WIDTH_PX = 560.0
MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP = 200.0, 310.0, 250.0
GAP_LABEL_SPACING = 30.0

COLOR_PERIMETER = "#455a64"
COLOR_REGULAR = "#1976d2"
COLOR_REPLACE = "#e65100"
COLOR_ADD = "#8e24aa"
COLOR_TEXT = "#111111"
COLOR_GAP = "#2e7d32"
FONT = "Arial, Helvetica, sans-serif"

KIND_COLORS = {KIND_END: COLOR_PERIMETER, KIND_REGULAR: COLOR_REGULAR, KIND_REPLACE: COLOR_REPLACE, KIND_ADD: COLOR_ADD}


def scale_for(result):
    """px uz mm: viens mērogs visam zīmējumam; ierobežots tā, lai shēma paliek ritināma un ne pārāk plata."""
    return min(MAX_SCALE_PX_PER_MM, MAX_HEIGHT_PX / result.length_mm, MAX_WIDTH_PX / result.width_mm)


def _n(value):
    return f"{float(value):.2f}"


def _text(x, y, content, size=26, anchor="start", weight="normal", fill=COLOR_TEXT, extra=""):
    return (f'<text x="{_n(x)}" y="{_n(y)}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}" {extra}>{escape(str(content))}</text>')


def build_frame_svg(result) -> str:
    """SVG virkne pilnam modulim (perimetra sijas, regulārās, pastiprinājumi, asis no gala, atstarpes, leģenda)."""
    k = scale_for(result)
    p = result.params.perimeter_width_mm
    length, width = result.length_mm, result.width_mm
    x0, y0 = MARGIN_LEFT, MARGIN_TOP
    frame_w, frame_h = width * k, length * k
    span_x0 = x0 + p * k                       # gala/šķērssiju sākums pa x
    span_w = (width - 2 * p) * k

    parts = []
    # --- garās perimetra sijas (visā L) ---
    for side, x in (("kreisā", x0), ("labā", x0 + (width - p) * k)):
        parts.append(f'<rect data-kind="long" data-side="{side}" data-start="0" data-end="{length}" '
                     f'x="{_n(x)}" y="{_n(y0)}" width="{_n(p * k)}" height="{_n(frame_h)}" fill="{COLOR_PERIMETER}" '
                     f'stroke="#263238" stroke-width="1"/>')
    # --- sijas pa garumu: gala sijas, regulārās, pastiprinājumi ---
    for m in result.members:
        y = y0 + float(m.start) * k
        h = float(m.end - m.start) * k
        attrs = (f'data-kind="{m.kind}" data-label="{m.label}" data-start="{format_axis(m.start)}" '
                 f'data-end="{format_axis(m.end)}"')
        if m.axis is not None:
            attrs += f' data-axis="{format_axis(m.axis)}"'
        if m.number is not None:
            attrs += f' data-number="{m.number}"'
        parts.append(f'<rect {attrs} x="{_n(span_x0)}" y="{_n(y)}" width="{_n(span_w)}" height="{_n(h)}" '
                     f'fill="{KIND_COLORS[m.kind]}" stroke="#102027" stroke-width="0.6"/>')
    # --- uzraksti pie sijām: kolonna pa labi no atstarpju joslas (atstarpes ir tuvāk rāmim) ---
    gap_x = x0 + frame_w + 6                  # zaļā atstarpju josla
    tag_x = x0 + frame_w + 118                # sijas apzīmējumi (R1…, P1…)
    for m in result.members:
        if m.kind == KIND_END:
            continue
        cy = y0 + float((m.start + m.end) / 2) * k
        if m.kind == KIND_REGULAR:
            parts.append(_text(tag_x, cy + 9, m.label, size=24, fill=COLOR_REGULAR))
        else:
            tag = m.label + (f" aizv. R{m.number}" if m.kind == KIND_REPLACE else " papildus")
            parts.append(_text(tag_x, cy + 10, tag, size=28, weight="bold",
                               fill=COLOR_REPLACE if m.kind == KIND_REPLACE else COLOR_ADD))
    # --- asis no gala (kreisā puse): atzīmes pie pastiprinājumiem ---
    ruler_x = x0 - 22
    parts.append(f'<line x1="{_n(ruler_x)}" y1="{_n(y0)}" x2="{_n(ruler_x)}" y2="{_n(y0 + frame_h)}" stroke="{COLOR_TEXT}" stroke-width="2"/>')
    for value, label in ((0, "0"), (length, str(length))):
        y = y0 + value * k
        parts.append(f'<line x1="{_n(ruler_x - 9)}" y1="{_n(y)}" x2="{_n(ruler_x + 9)}" y2="{_n(y)}" stroke="{COLOR_TEXT}" stroke-width="2"/>')
        parts.append(_text(ruler_x - 14, y + (9 if value == 0 else -2), label, size=24, anchor="end"))
    for pl in result.reinforcements:
        y = y0 + float(pl.axis) * k
        color = COLOR_REPLACE if pl.mode == "replace" else COLOR_ADD
        parts.append(f'<line x1="{_n(ruler_x - 9)}" y1="{_n(y)}" x2="{_n(x0 + frame_w)}" y2="{_n(y)}" stroke="{color}" '
                     f'stroke-width="1.5" stroke-dasharray="8 6" data-kind="axis" data-label="{pl.label}" data-axis="{format_axis(pl.axis)}"/>')
        parts.append(_text(ruler_x - 14, y + 10, f"{pl.label} {format_axis(pl.axis)}", size=26, anchor="end",
                           weight="bold", fill=color, extra=f'data-kind="axis-label" data-label="{pl.label}"'))
    # --- atstarpes: josla pie rāmja + īss skaitlis (pie pastiprinājumiem un gala atlikums); uzraksti netiek pārklāti ---
    last = len(result.gaps) - 1
    labels = []
    for index, gap in enumerate(result.gaps):
        near_rf = gap.left.startswith("P") or gap.right.startswith("P")
        if not (near_rf or index == last):
            continue
        left = next(m for m in result.members if m.label == gap.left)
        top, bottom = y0 + float(left.end) * k, y0 + float(left.end + gap.size) * k
        parts.append(f'<line data-kind="gap" data-from="{gap.left}" data-to="{gap.right}" data-size="{format_axis(gap.size)}" '
                     f'x1="{_n(gap_x)}" y1="{_n(top)}" x2="{_n(gap_x)}" y2="{_n(bottom)}" stroke="{COLOR_GAP}" stroke-width="4"/>')
        if index == last:
            text = f"atl. {format_axis(gap.size)}" + ("*" if gap.size != result.remainder_mm else "")
        else:
            text = format_axis(gap.size)
        labels.append([(top + bottom) / 2, text, (top + bottom) / 2])
    labels.sort(key=lambda item: item[0])
    for i in range(1, len(labels)):                       # uzrakstu atdalīšana: nepārklājas savā starpā
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + GAP_LABEL_SPACING)
    for y, text, origin in labels:
        if abs(y - origin) > 3:
            parts.append(f'<line x1="{_n(gap_x)}" y1="{_n(origin)}" x2="{_n(gap_x + 12)}" y2="{_n(y)}" stroke="{COLOR_GAP}" stroke-width="1.5"/>')
        parts.append(_text(gap_x + 14, y + 9, text, size=24, fill=COLOR_GAP, weight="bold", extra='data-kind="gap-label"'))
    # --- izmēru norādes: W virs shēmas, L pie kreisās malas, mēroga lineāls ---
    wy = y0 - 26
    parts.append(f'<line x1="{_n(x0)}" y1="{_n(wy)}" x2="{_n(x0 + frame_w)}" y2="{_n(wy)}" stroke="{COLOR_TEXT}" stroke-width="2"/>')
    for x in (x0, x0 + frame_w):
        parts.append(f'<line x1="{_n(x)}" y1="{_n(wy - 9)}" x2="{_n(x)}" y2="{_n(wy + 9)}" stroke="{COLOR_TEXT}" stroke-width="2"/>')
    parts.append(_text(x0 + frame_w / 2, wy - 16, f"W = {width} mm", size=30, anchor="middle", weight="bold"))
    bar = 1000 * k
    by = y0 + frame_h + 46
    parts.append(f'<line data-kind="scale-bar" data-mm="1000" x1="{_n(x0)}" y1="{_n(by)}" x2="{_n(x0 + bar)}" y2="{_n(by)}" '
                 f'stroke="{COLOR_TEXT}" stroke-width="4"/>')
    parts.append(_text(x0 + bar + 12, by + 8, "1000 mm (mērogs)", size=22))

    # --- virsraksts ---
    header = [
        _text(20, 42, f"Grīdas rāmis: {result.name}", size=34, weight="bold"),
        _text(20, 86, f"L = {length} mm (vertikāli), W = {width} mm", size=28),
        _text(20, 124, f"Sijas kopā: {result.total_pieces} gab. · atlikums (pamatrāmis): {result.remainder_mm} mm", size=26),
        _text(20, 160, ("Lietotāja pastiprinājumi: " + str(result.reinforcement_count)) if result.reinforcements
              else "Pastiprinājumi nav norādīti (pamatrāmja aprēķins)", size=26, weight="bold"),
    ]

    # --- leģenda (teksts tiek ietīts, lai nepārsniegtu shēmas platumu) ---
    legend_y = by + 64
    items = [(COLOR_PERIMETER, f"Perimetra sijas {p}×{result.params.beam_height_mm} (garās + gala)"),
             (COLOR_REGULAR, f"Regulārās šķērssijas {result.params.cross_width_mm}×{result.params.beam_height_mm} (pamatrāmis)")]
    if result.replaced_count:
        items.append((COLOR_REPLACE, "Pastiprinājums 150×240: AIZVIETO regulāro (lietotāja norādīts)"))
    if result.added_count:
        items.append((COLOR_ADD, "Pastiprinājums 150×240: PAPILDUS (lietotāja norādīts)"))
    items.append((COLOR_GAP, "Brīvā atstarpe, mm (atl. = gala atlikums)"))
    legend = [_text(20, legend_y, "Leģenda", size=30, weight="bold")]
    y = legend_y + 18
    for color, label in items:
        lines = textwrap.wrap(label, 44)
        legend.append(f'<rect data-kind="legend" x="20" y="{_n(y)}" width="34" height="28" fill="{color}" stroke="#102027" stroke-width="1"/>')
        for line in lines:
            legend.append(_text(68, y + 22, line, size=26))
            y += 34
        y += 10
    notes = [CONVENTION_NOTE, "Pastiprinājumi ir LIETOTĀJA norādīti; automātiska noteikšana un 45×240 īsās starpsijas "
             "nav realizētas. Provizorisks aprēķins, nevis konstruktora specifikācija."]
    if any(g.size != result.remainder_mm for g in result.gaps[-1:]):
        notes.insert(0, f"* gala atlikums mainīts ar pastiprinājumu; pamatrāmja atlikums {result.remainder_mm} mm.")
    y += 6
    for note in notes:
        for line in textwrap.wrap(note, 52):
            legend.append(_text(20, y + 20, line, size=22, fill="#37474f"))
            y += 28
        y += 8
    note_y = y

    total_w = x0 + frame_w + MARGIN_RIGHT
    total_h = note_y + 16
    desc = (f"Grīdas rāmja shēma: L {length} mm, W {width} mm, {result.regular_count} regulārās, "
            f"{result.replaced_count} aizvietotās, {result.added_count} papildus pastiprinājuma sijas.")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" role="img" width="{_n(total_w)}" height="{_n(total_h)}" '
            f'style="width:100%;height:auto;max-width:{_n(total_w)}px;display:block" viewBox="0 0 {_n(total_w)} {_n(total_h)}" data-scale-px-per-mm="{k:.6f}" data-length-mm="{length}" '
            f'data-width-mm="{width}" data-origin-x="{_n(x0)}" data-origin-y="{_n(y0)}">'
            f'<title>{escape(result.name)}</title><desc>{escape(desc)}</desc>'
            f'<rect x="0" y="0" width="{_n(total_w)}" height="{_n(total_h)}" fill="#ffffff"/>'
            + "".join(header) + "".join(parts) + "".join(legend) + "</svg>")
