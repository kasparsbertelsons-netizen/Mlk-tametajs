"""Grīdas rāmja pastiprinājuma sijas 150×240: LIETOTĀJA manuāli norādītas un apstiprinātas pozīcijas (Issue #10).

Tīrs modulis bez Streamlit/PDF atkarības. NEATPAZĪST nesošas sienas un NEnosaka pastiprinājumus automātiski:
pozīcijas ievada un apstiprina lietotājs katram modulim. Aprēķins ir provizorisks, nevis konstruktora specifikācija.

Noteikumi:
- Pastiprinājums: 150×240 mm, pilns laidums = W − 2 × perimetra sijas platums (tāds pats garums kā šķērssijām).
- IEVADES KONVENCIJA (prototips): ass = sijas CENTRA koordināta garenvirzienā, mm no moduļa ĀRĒJĀ gala, tā paša
  gala, no kura skaita regulārās šķērssijas (shēmā augšā). Piemērs: pirmās regulārās šķērssijas ass ir 822,5 mm.
- Ja pastiprinājuma ass PRECĪZI sakrīt ar regulārās šķērssijas asi, tā tiek AIZVIETOTA; citādi pastiprinājums tiek
  PIEVIENOTS, nepārbīdot esošās regulārās sijas un nepārdalot pamatrāmja soli.
- Nekādas noapaļošanas vai piesnapošanas: koordināta tiek lietota tieši (`Fraction`); 822,0 vai 823,0 NEaizvieto sijas
  ar asi 822,5, bet pārklājas ar to un tiek bloķēts.
- Pārklāšanās ar citu siju, gala siju vai ārpus brīvā rāmja, kā arī atkārtota viena un tā pati koordināta BLOĶĒ pilnu
  aprēķinu ar skaidrojumu; risinājums netiek izdomāts. Sijas, kas tikai pieskaras (atstarpe 0), nepārklājas, bet
  tiek atzīmētas "jāpārbauda".
"""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import isfinite
from numbers import Real

RF_WIDTH_MM = 150
RF_HEIGHT_MM = 240
MAX_DECIMALS = 2                 # koordināta līdz 0,01 mm; precīzāka ievade tiek noraidīta, nevis noapaļota
MAX_REINFORCEMENTS = 20
RF_SOURCE_USER = "Lietotāja manuāli norādīts un apstiprināts (nav nolasīts no PDF)"
CONVENTION_NOTE = ("Ass = sijas centra koordināta garenvirzienā, mm no moduļa ārējā gala (tā paša gala, no kura skaita "
                   "regulārās šķērssijas; shēmā augšā).")

KIND_END = "end"                 # gala sija (moduļa gals)
KIND_REGULAR = "regular"         # regulārā šķērssija 45×240
KIND_REPLACE = "reinforcement_replace"
KIND_ADD = "reinforcement_add"

CODE_DUPLICATE = "DUPLICATE_AXIS"
CODE_OUTSIDE = "OUTSIDE_FREE_FRAME"
CODE_OVERLAP_REGULAR = "OVERLAP_REGULAR"
CODE_OVERLAP_REINFORCEMENT = "OVERLAP_REINFORCEMENT"
CODE_UNSUPPORTED_PARAMS = "UNSUPPORTED_PARAMS"
CODE_TOO_MANY = "TOO_MANY"


@dataclass(frozen=True)
class Conflict:
    code: str
    message: str
    axis: object = None              # Fraction vai None


class ReinforcementError(ValueError):
    """Pastiprinājumu pozīcijas ir pretrunā: pilns aprēķins ir bloķēts. `conflicts` satur skaidrojumus."""

    def __init__(self, conflicts):
        self.conflicts = tuple(conflicts)
        super().__init__(" | ".join(c.message for c in self.conflicts))


@dataclass(frozen=True)
class Member:
    kind: str
    label: str
    start: Fraction                  # mm no moduļa ārējā gala
    end: Fraction
    axis: object = None              # Fraction (sijas centrs)
    number: object = None            # regulārās sijas Nr. (1-based) vai aizvietotās sijas Nr.


@dataclass(frozen=True)
class Placement:
    label: str                       # P1, P2 … pēc ass augošā secībā
    axis: Fraction
    start: Fraction
    end: Fraction
    mode: str                        # "replace" | "add"
    replaces: object = None          # aizvietotās regulārās sijas Nr. (1-based)


@dataclass(frozen=True)
class Gap:
    left: str
    right: str
    size: Fraction                   # brīvā atstarpe mm starp blakus esošām sijām


# --- koordinātas ----------------------------------------------------------------------------------------
def parse_axis(value) -> Fraction:
    """Precīza koordināta mm. Pieņem int, Fraction, Decimal, float (pēc īsākās decimālās pierakstes), str ("822,5").

    Noraida bool, NaN/∞, nepareizu tekstu un ievadi ar vairāk nekā 2 zīmēm aiz komata (netiek noapaļota).
    """
    if isinstance(value, bool):
        raise ValueError("Ass: jābūt skaitlim milimetros.")
    try:
        if isinstance(value, Fraction):
            fraction = value
        elif isinstance(value, int):
            fraction = Fraction(value)
        elif isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError
            fraction = Fraction(value)
        elif isinstance(value, float):
            if not isfinite(value):
                raise ValueError
            fraction = Fraction(repr(value))
        elif isinstance(value, str):
            text = value.strip().replace(",", ".")
            if not text or not all(c.isdigit() or c in ".-+" for c in text) or text.count(".") > 1:
                raise ValueError
            fraction = Fraction(text)
        elif isinstance(value, Real):
            fraction = Fraction(value)
        else:
            raise ValueError
    except (ValueError, ZeroDivisionError, OverflowError):
        raise ValueError(f"Ass: nederīga vērtība (jābūt skaitlim milimetros, līdz {MAX_DECIMALS} zīmēm aiz komata).") from None
    if (fraction * 10 ** MAX_DECIMALS).denominator != 1:
        raise ValueError(f"Ass: ne vairāk par {MAX_DECIMALS} zīmēm aiz komata; koordināta netiek noapaļota.")
    if fraction <= 0:
        raise ValueError("Ass: jābūt pozitīvai (mm no moduļa ārējā gala).")
    return fraction


def format_axis(value) -> str:
    """"822.5", "1150", "1467.25": precīza pieraksts bez liekām nullēm."""
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.{MAX_DECIMALS}f}".rstrip("0").rstrip(".")


# --- plānošana ----------------------------------------------------------------------------------------------
def _overlap(a_start, a_end, b_start, b_end):
    """Pozitīva garuma šķēlums (pieskaršanās nav pārklāšanās)."""
    return a_start < b_end and b_start < a_end


def plan_layout(length_mm, perimeter_mm, cross_width_mm, regular_starts, axes, *, rf_width_mm=RF_WIDTH_MM):
    """(placements, members, gaps) vai ReinforcementError.

    `regular_starts` — pamatrāmja regulāro šķērssiju sākumi (mm no gala), `axes` — Fraction saraksts.
    Bez pastiprinājumiem atgriež pamatrāmja izkārtojumu (gala sijas + regulārās).
    """
    perimeter, rf_half = Fraction(perimeter_mm), Fraction(rf_width_mm) / 2
    free_lo, free_hi = perimeter, Fraction(length_mm) - perimeter
    regulars = [(n, Fraction(s), Fraction(s) + cross_width_mm, Fraction(s) + Fraction(cross_width_mm, 2))
                for n, s in enumerate(regular_starts, 1)]
    centers = {c: n for n, _s, _e, c in regulars}
    conflicts = []
    if len(axes) > MAX_REINFORCEMENTS:
        conflicts.append(Conflict(CODE_TOO_MANY, f"Pastiprinājumu skaits pārsniedz {MAX_REINFORCEMENTS} vienam modulim."))
        raise ReinforcementError(conflicts)

    seen, duplicates = set(), []
    for axis in axes:
        if axis in seen and axis not in duplicates:
            duplicates.append(axis)
        seen.add(axis)
    for axis in duplicates:
        conflicts.append(Conflict(
            CODE_DUPLICATE, f"Ass {format_axis(axis)} mm ir ievadīta vairākkārt: viena un tā pati koordināta nedrīkst "
            "radīt dublikātu. Atstājiet vienu ierakstu.", axis))

    unique = sorted(seen)
    placements, replaced = [], set()
    for number, axis in enumerate(unique, 1):
        start, end = axis - rf_half, axis + rf_half
        mode, replaces = "add", None
        if axis in centers:
            mode, replaces = "replace", centers[axis]
            replaced.add(replaces)
        placements.append(Placement(f"P{number}", axis, start, end, mode, replaces))

    for p in placements:
        text = f"Ass {format_axis(p.axis)} mm (sija {format_axis(p.start)}–{format_axis(p.end)} mm)"
        if p.start < free_lo or p.end > free_hi:
            where = []
            if p.start < free_lo:
                where.append(f"sākas pie {format_axis(p.start)} mm, bet brīvais rāmis sākas pie {format_axis(free_lo)} mm "
                             "(pārklājas ar gala siju vai iet ārpus moduļa)")
            if p.end > free_hi:
                where.append(f"beidzas pie {format_axis(p.end)} mm, bet brīvais rāmis beidzas pie {format_axis(free_hi)} mm "
                             "(pārklājas ar gala siju vai iet ārpus moduļa)")
            conflicts.append(Conflict(CODE_OUTSIDE, f"{text} ir ārpus brīvā rāmja: " + "; ".join(where) + ".", p.axis))
        for number, r_start, r_end, r_center in regulars:
            if number not in replaced and _overlap(p.start, p.end, r_start, r_end):
                conflicts.append(Conflict(
                    CODE_OVERLAP_REGULAR,
                    f"{text} pārklājas ar regulāro šķērssiju Nr. {number} (ass {format_axis(r_center)} mm, "
                    f"{format_axis(r_start)}–{format_axis(r_end)} mm). Aizvietošana notiek tikai tad, ja ass PRECĪZI sakrīt "
                    f"ar regulārās sijas asi ({format_axis(r_center)} mm); koordināta netiek noapaļota vai pārbīdīta.", p.axis))
    for i, a in enumerate(placements):
        for b in placements[i + 1:]:
            if _overlap(a.start, a.end, b.start, b.end):
                conflicts.append(Conflict(
                    CODE_OVERLAP_REINFORCEMENT,
                    f"Pastiprinājumi ar asīm {format_axis(a.axis)} mm un {format_axis(b.axis)} mm pārklājas "
                    f"(attālums {format_axis(b.axis - a.axis)} mm ir mazāks par sijas platumu {rf_width_mm} mm).", a.axis))
    if conflicts:
        raise ReinforcementError(conflicts)

    members = [Member(KIND_END, "G1", Fraction(0), perimeter, None, None)]
    for number, r_start, r_end, r_center in regulars:
        if number not in replaced:
            members.append(Member(KIND_REGULAR, f"R{number}", r_start, r_end, r_center, number))
    for p in placements:
        kind = KIND_REPLACE if p.mode == "replace" else KIND_ADD
        members.append(Member(kind, p.label, p.start, p.end, p.axis, p.replaces))
    members.append(Member(KIND_END, "G2", free_hi, Fraction(length_mm), None, None))
    members.sort(key=lambda m: (m.start, m.end))
    gaps = tuple(Gap(a.label, b.label, b.start - a.end) for a, b in zip(members, members[1:]))
    return tuple(placements), tuple(members), gaps
