"""Moduļa grīdas PAMATRĀMJA aprēķina kodols (Issue #4).

Tīrs modulis: nav atkarīgs ne no Streamlit, ne no PDF. Ģeometrijas atpazīšana
(PDF → L, W) ir atsevišķi (`src/ad_plan.py`); šeit tikai apstiprinātu izmēru
aprēķins.

Apstiprinātie noteikumi (ChatGPT, Issue #2 / #4):
- 2 garās perimetra sijas 200×240 mm visā garumā L;
- 2 gala sijas 200×240 mm, garums W − 2·perimetrs (W − 400);
- regulārās šķērssijas 45×240 mm, garums W − 400;
- mērījums no gala sijas iekšējās plaknes: 600 mm brīvas atstarpes līdz pirmās
  šķērssijas malai, tālāk 645 mm solis (600 + 45); n = ⌊(L − 400) / 645⌋;
- pēdējā atstarpe ir atlikums: sija netiek pievienota automātiski un atstarpes
  netiek pārdalītas;
- atlikums > 600 mm vai = 0 → brīdinājums "jāpārbauda".

Aprēķins ir provizorisks, nav konstruktora specifikācija, un ietver TIKAI
pamatrāmi (bez 150×240 pastiprinājumiem un 45×240 īsajām starpsijām).
"""
import dataclasses
from dataclasses import dataclass, field
from fractions import Fraction
from numbers import Integral, Real
from math import isfinite

from src.reinforcement import (
    KIND_ADD, KIND_REPLACE, RF_HEIGHT_MM, RF_SOURCE_USER, RF_WIDTH_MM, Conflict, ReinforcementError,
    format_axis, parse_axis, plan_layout,
)

PERIMETER_WIDTH_MM = 200
BEAM_HEIGHT_MM = 240
CROSS_WIDTH_MM = 45
CLEAR_GAP_MM = 600
WIDTH_REVIEW_LIMIT_MM = 4500   # orientējoša robeža, nevis absolūta
MAX_DIMENSION_MM = 100_000     # aizsardzība pret absurdiem ievaddatiem

SCOPE_NOTE = (
    "Rezultāts ietver tikai pamatrāmi (2 garās, 2 gala un regulārās šķērssijas). "
    "150×240 pastiprinājumi un 45×240 īsās starpsijas NAV automātiski noteiktas "
    "un NAV ieskaitītas, tāpēc kopējais apjoms var būt par mazu. Aprēķins ir "
    "provizorisks, nevis konstruktora specifikācija."
)

SCOPE_NOTE_REINFORCED = (
    "Rezultāts ietver pamatrāmi (2 garās, 2 gala un regulārās šķērssijas) un LIETOTĀJA manuāli norādītos un apstiprinātos "
    "150×240 pastiprinājumus. Automātiska pastiprinājumu noteikšana un 45×240 īsās starpsijas NAV realizētas un NAV "
    "ieskaitītas, tāpēc kopējais apjoms var būt par mazu. Aprēķins ir provizorisks, nevis konstruktora specifikācija."
)
VOLUME_SCOPE_BASE = ("Pamatrāmis: perimetra, gala un regulārās šķērssijas; BEZ 150×240 pastiprinājumiem un BEZ 45×240 "
                     "īsajām starpsijām")
VOLUME_SCOPE_REINFORCED = ("Pamatrāmis + LIETOTĀJA manuāli norādītie 150×240 pastiprinājumi; BEZ automātiski noteiktiem "
                           "pastiprinājumiem, BEZ 45×240 īsajām starpsijām un BEZ zāģēšanas atgriezumiem")

ELEMENT_RF_REPLACE = "Pastiprinājums 150×240 (aizvieto regulāro)"
ELEMENT_RF_ADD = "Pastiprinājums 150×240 (papildus)"
ELEMENT_LONG = "Garās perimetra sijas"
ELEMENT_END = "Gala sijas"
ELEMENT_CROSS = "Regulārās šķērssijas"


@dataclass(frozen=True)
class FrameParams:
    """Rāmja parametri. Noklusējums ir Rebel standarts, nevis nolasīts no rasējuma."""
    perimeter_width_mm: int = PERIMETER_WIDTH_MM
    beam_height_mm: int = BEAM_HEIGHT_MM
    cross_width_mm: int = CROSS_WIDTH_MM
    clear_gap_mm: int = CLEAR_GAP_MM

    @property
    def pitch_mm(self) -> int:
        return self.clear_gap_mm + self.cross_width_mm


DEFAULT_PARAMS = FrameParams()


@dataclass(frozen=True)
class FrameWarning:
    code: str
    message: str


@dataclass(frozen=True)
class BeamRow:
    element: str
    width_mm: int
    height_mm: int
    length_mm: int
    count: int
    basis: str

    @property
    def volume_mm3(self) -> int:
        return self.width_mm * self.height_mm * self.length_mm * self.count

    @property
    def volume_m3(self) -> float:
        return round(self.volume_mm3 / 1e9, 6)

    def to_dict(self) -> dict:
        return {"Elements": self.element, "b (mm)": self.width_mm, "h (mm)": self.height_mm,
                "L (mm)": self.length_mm, "Gab.": self.count, "m³": self.volume_m3,
                "Pamatojums": self.basis}


@dataclass(frozen=True)
class ModuleResult:
    name: str
    source: str
    length_mm: int
    width_mm: int
    params: FrameParams
    params_default: bool
    clear_length_mm: int            # L − 2·perimetrs: brīvais garums starp gala sijām
    cross_count: int
    remainder_mm: int               # pēdējā atstarpe, bez pārdalīšanas
    rows: tuple
    cross_positions: tuple          # ((sākums, beigas), …) mm no moduļa gala: PAMATRĀMJA regulārās šķērssijas
    warnings: tuple = field(default_factory=tuple)
    reinforcements: tuple = ()      # Placement: lietotāja norādītie 150×240 pastiprinājumi (izvēles)
    members: tuple = ()             # Member: gala sijas + atlikušās regulārās + pastiprinājumi, sakārtoti pa garumu
    gaps: tuple = ()                # Gap: brīvās atstarpes starp blakus esošām sijām (arī ar pastiprinājumiem)
    reinforcement_source: str = ""

    @property
    def replaced_count(self) -> int:
        return sum(1 for r in self.reinforcements if r.mode == "replace")

    @property
    def added_count(self) -> int:
        return sum(1 for r in self.reinforcements if r.mode == "add")

    @property
    def reinforcement_count(self) -> int:
        return len(self.reinforcements)

    @property
    def regular_count(self) -> int:
        """Atlikušās regulārās šķērssijas (pamatrāmja skaits mīnus aizvietotās)."""
        return self.cross_count - self.replaced_count

    @property
    def regular_axes(self) -> tuple:
        """Pamatrāmja regulāro šķērssiju asis (centri), mm no moduļa ārējā gala; precīzi (Fraction)."""
        half = Fraction(self.params.cross_width_mm, 2)
        return tuple(Fraction(start) + half for start, _end in self.cross_positions)

    @property
    def total_pieces(self) -> int:
        return sum(row.count for row in self.rows)

    @property
    def total_volume_mm3(self) -> int:
        return sum(row.volume_mm3 for row in self.rows)

    @property
    def total_volume_m3(self) -> float:
        return round(self.total_volume_mm3 / 1e9, 6)

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings)

    @property
    def notes(self) -> tuple:
        if self.params_default:
            notes = (f"Perimetra sija {self.params.perimeter_width_mm}×"
                     f"{self.params.beam_height_mm} mm ir NOKLUSĒJUMS, nav nolasīts no rasējuma.",)
        else:
            notes = ("Izmantoti lietotāja apstiprināti nestandarta parametri.",)
        if self.reinforcements:
            notes += (f"Pastiprinājumi ({self.reinforcement_count}) ir LIETOTĀJA manuāli norādīti un apstiprināti, "
                      "nav nolasīti no PDF; automātiska pastiprinājumu noteikšana un 45×240 īsās starpsijas nav realizētas.",)
        else:
            notes += ("Pastiprinājumi nav norādīti: tas ir pamatrāmja aprēķins, nevis pierādījums, ka pastiprinājumi "
                      "nav vajadzīgi.",)
        return notes

    @property
    def volume_scope(self) -> str:
        return VOLUME_SCOPE_REINFORCED if self.reinforcements else VOLUME_SCOPE_BASE


@dataclass(frozen=True)
class ModuleSpec:
    length_mm: object
    width_mm: object
    name: str = "Modulis"
    source: str = "Ievadīts manuāli"
    params: FrameParams = DEFAULT_PARAMS
    nonstandard_confirmed: bool = False
    reinforcements: tuple = ()
    reinforcement_source: str = RF_SOURCE_USER


def scope_note(with_reinforcements: bool) -> str:
    return SCOPE_NOTE_REINFORCED if with_reinforcements else SCOPE_NOTE


def _mm(value, label):
    """Vesels pozitīvs skaits milimetros; citādi ValueError."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label}: jābūt skaitlim milimetros.")
    if not isinstance(value, Integral):
        if not isfinite(value) or float(value) != int(value):
            raise ValueError(f"{label}: jābūt veselam skaitlim milimetros (saņemts {value}).")
    value = int(value)
    if value <= 0:
        raise ValueError(f"{label}: jābūt pozitīvam (saņemts {value} mm).")
    if value > MAX_DIMENSION_MM:
        raise ValueError(f"{label}: {value} mm pārsniedz pieļaujamo {MAX_DIMENSION_MM} mm.")
    return value


def _validated_params(params):
    if not isinstance(params, FrameParams):
        raise ValueError("Parametriem jābūt FrameParams.")
    return FrameParams(
        _mm(params.perimeter_width_mm, "Perimetra sijas platums"),
        _mm(params.beam_height_mm, "Siju augstums"),
        _mm(params.cross_width_mm, "Šķērssijas platums"),
        _mm(params.clear_gap_mm, "Brīvā atstarpe"),
    )


def calculate_module(length_mm, width_mm, *, name="Modulis", source="Ievadīts manuāli",
                     params=DEFAULT_PARAMS, nonstandard_confirmed=False, reinforcements=(),
                     reinforcement_source=RF_SOURCE_USER) -> ModuleResult:
    """Viena taisnstūra moduļa pamatrāmis no APSTIPRINĀTIEM L un W (mm) + izvēles LIETOTĀJA pastiprinājumi.

    `reinforcements`: pastiprinājumu asis (mm no moduļa ārējā gala, sijas CENTRS; skat. `src/reinforcement.py`);
    tukšs = tikai pamatrāmis (rezultāts nemainīts). Izmet ValueError nederīgiem izmēriem/asīm un nestandarta
    parametriem bez apstiprinājuma, un `ReinforcementError` (ValueError apakšklase) pozīciju konfliktiem.
    """
    length = _mm(length_mm, "Garums L")
    width = _mm(width_mm, "Platums W")
    params = _validated_params(params)
    is_default = params == DEFAULT_PARAMS
    if not is_default and not nonstandard_confirmed:
        raise ValueError("Nestandarta rāmja parametri nav apstiprināti; aprēķins netiek veikts.")

    p = params.perimeter_width_mm
    span = width - 2 * p       # gala un šķērssiju garums
    clear = length - 2 * p     # brīvais garums starp gala sijām
    if span <= 0:
        raise ValueError(f"Platums W ({width} mm) ir par mazu: jābūt lielākam par 2 × perimetrs "
                         f"({2 * p} mm), lai gala sijām būtu pozitīvs garums.")
    if clear <= 0:
        raise ValueError(f"Garums L ({length} mm) ir par mazs: jābūt lielākam par 2 × perimetrs "
                         f"({2 * p} mm).")

    pitch = params.pitch_mm
    count = clear // pitch
    remainder = clear - count * pitch
    gap, cross_w = params.clear_gap_mm, params.cross_width_mm
    positions = tuple((p + gap + k * pitch, p + gap + k * pitch + cross_w) for k in range(count))

    axes = [parse_axis(value) for value in reinforcements]
    if axes and params.beam_height_mm != RF_HEIGHT_MM:
        raise ReinforcementError([Conflict(
            "UNSUPPORTED_PARAMS",
            f"Pastiprinājuma recepte {RF_WIDTH_MM}×{RF_HEIGHT_MM} ir apstiprināta tikai rāmja augstumam {RF_HEIGHT_MM} mm; "
            f"rāmja augstums {params.beam_height_mm} mm netiek interpretēts automātiski.")])
    placements, members, gaps = plan_layout(length, p, cross_w, [start for start, _end in positions], axes)
    replaced = sum(1 for pl in placements if pl.mode == "replace")
    added = len(placements) - replaced

    basis = "Noklusējums" if is_default else "Apstiprināti nestandarta parametri"
    rows = [
        BeamRow(ELEMENT_LONG, p, params.beam_height_mm, length, 2, f"{basis}: visā garumā L"),
        BeamRow(ELEMENT_END, p, params.beam_height_mm, span, 2, f"{basis}: W − 2 × perimetrs"),
        BeamRow(ELEMENT_CROSS, cross_w, params.beam_height_mm, span, count - replaced,
                f"{basis}: {gap} mm brīva atstarpe, {pitch} mm solis; atlikums bez pārdalīšanas"
                + (f"; {replaced} aizvietota(s) ar pastiprinājumu" if replaced else "")),
    ]
    rf_basis = (f"{reinforcement_source}: {RF_WIDTH_MM}×{RF_HEIGHT_MM}, pilns laidums W − 2 × perimetrs")
    if replaced:
        rows.append(BeamRow(ELEMENT_RF_REPLACE, RF_WIDTH_MM, RF_HEIGHT_MM, span, replaced,
                            f"{rf_basis}; AIZVIETO regulāro siju (ass precīzi sakrīt)"))
    if added:
        rows.append(BeamRow(ELEMENT_RF_ADD, RF_WIDTH_MM, RF_HEIGHT_MM, span, added,
                            f"{rf_basis}; PAPILDUS (regulārās sijas netiek pārbīdītas)"))
    rows = tuple(rows)

    warnings = []
    if width > WIDTH_REVIEW_LIMIT_MM:
        warnings.append(FrameWarning(
            "WIDTH_OVER_LIMIT",
            f"Platums {width} mm pārsniedz orientējošo {WIDTH_REVIEW_LIMIT_MM} mm: jāpārbauda "
            "un jāapstiprina. Robeža nav absolūta."))
    if count == 0:
        warnings.append(FrameWarning(
            "NO_CROSS_JOISTS", f"Brīvajā garumā {clear} mm neietilpst neviena šķērssija: jāpārbauda."))
    if remainder > gap:
        warnings.append(FrameWarning(
            "REMAINDER_OVER_GAP",
            f"Atlikums {remainder} mm pārsniedz {gap} mm: jāpārbauda. Sija netiek pievienota "
            "automātiski un atstarpes netiek pārdalītas."))
    if remainder == 0:
        warnings.append(FrameWarning(
            "REMAINDER_ZERO",
            "Atlikums 0 mm: pēdējā šķērssija piekļaujas gala sijai: jāpārbauda; "
            "nav apstiprināts kā konstruktīvi derīgs."))
    if not is_default:
        warnings.append(FrameWarning(
            "NONSTANDARD_PARAMS", "Izmantoti nestandarta parametri (lietotāja apstiprināti)."))
    for gap_item in gaps:
        touches = {gap_item.left, gap_item.right} & {pl.label for pl in placements}
        if gap_item.size == 0 and touches:
            warnings.append(FrameWarning(
                "REINFORCEMENT_ZERO_GAP",
                f"Pastiprinājums {', '.join(sorted(touches))} pieskaras blakus sijai ({gap_item.left} / {gap_item.right}): "
                "atstarpe 0 mm: jāpārbauda; nav apstiprināts kā konstruktīvi derīgs."))

    result = ModuleResult(
        name=name, source=source, length_mm=length, width_mm=width, params=params,
        params_default=is_default, clear_length_mm=clear, cross_count=count,
        remainder_mm=remainder, rows=rows, cross_positions=positions, warnings=tuple(warnings),
        reinforcements=placements, members=members, gaps=gaps,
        reinforcement_source=reinforcement_source if placements else "")
    problems = layout_problems(result) + members_problems(result)
    if problems:  # iekšēja pretruna = kļūda kodā, nevis lietotāja datos
        raise RuntimeError("Siju novietojuma pārbaude neizdevās: " + "; ".join(problems))
    return result


def members_problems(result: ModuleResult) -> list:
    """Neatkarīga GALĪGĀ izkārtojuma pārbaude (ar pastiprinājumiem): robežas, nepārklāšanās, skaiti, atstarpes."""
    problems = []
    p = result.params.perimeter_width_mm
    members = result.members
    if not members or members[0].start != 0 or members[-1].end != result.length_mm:
        problems.append("gala sijas neatrodas moduļa galos")
    for a, b in zip(members, members[1:]):
        if b.start < a.end:
            problems.append(f"{a.label} un {b.label} pārklājas")
    if [g.size for g in result.gaps] != [b.start - a.end for a, b in zip(members, members[1:])]:
        problems.append("atstarpes neatbilst izkārtojumam")
    regular = [m for m in members if m.kind == "regular"]
    if len(regular) != result.regular_count:
        problems.append("regulāro sijas skaits nesakrīt ar rindu")
    if sum(1 for m in members if m.kind == "reinforcement_replace") != result.replaced_count:
        problems.append("aizvietoto skaits nesakrīt")
    if sum(1 for m in members if m.kind == "reinforcement_add") != result.added_count:
        problems.append("papildus pastiprinājumu skaits nesakrīt")
    for m in members:
        if m.kind != "end" and (m.start < p or m.end > result.length_mm - p):
            problems.append(f"{m.label} ir ārpus brīvā rāmja")
    return problems


def layout_problems(result: ModuleResult) -> list:
    """Neatkarīga novietojuma pārbaude: robežas, nepārklāšanās, atstarpes. Tukšs saraksts = OK."""
    problems = []
    p, gap = result.params.perimeter_width_mm, result.params.clear_gap_mm
    cross_w, pitch = result.params.cross_width_mm, result.params.pitch_mm
    left_end, right_start = p, result.length_mm - p      # gala sijas: [0, p] un [L − p, L]
    positions = result.cross_positions

    if len(positions) != result.clear_length_mm // pitch:
        problems.append("šķērssiju skaits nesakrīt ar ⌊(L − 2p) / solis⌋")
    previous_end = left_end
    for index, (start, end) in enumerate(positions, 1):
        if end - start != cross_w:
            problems.append(f"{index}. šķērssijas platums nav {cross_w} mm")
        if start < left_end or end > right_start:
            problems.append(f"{index}. šķērssija pārklājas ar gala siju vai iziet ārpus rāmja")
        space = start - previous_end
        if space != gap:
            problems.append(f"atstarpe pirms {index}. šķērssijas ir {space} mm, nevis {gap} mm")
        previous_end = end
    last_gap = right_start - previous_end
    if last_gap != result.remainder_mm:
        problems.append(f"pēdējā atstarpe {last_gap} mm nesakrīt ar atlikumu {result.remainder_mm} mm")
    if not 0 <= result.remainder_mm < pitch:
        problems.append("atlikums ārpus intervāla [0, solis)")
    return problems


def calculate_modules(specs) -> list:
    """Katrs modulis tiek aprēķināts atsevišķi. Kļūdas ziņojumā tiek nosaukts modulis."""
    results = []
    for spec in specs:
        try:
            results.append(calculate_module(
                spec.length_mm, spec.width_mm, name=spec.name, source=spec.source,
                params=spec.params, nonstandard_confirmed=spec.nonstandard_confirmed,
                reinforcements=spec.reinforcements, reinforcement_source=spec.reinforcement_source))
        except ReinforcementError as error:
            raise ReinforcementError(
                [dataclasses.replace(c, message=f"{spec.name}: {c.message}") for c in error.conflicts]) from error
        except ValueError as error:
            raise ValueError(f"{spec.name}: {error}") from error
    return results


def summarize_modules(results) -> dict:
    """Moduļu kopsumma (moduļi summēti atsevišķi, tad saskaitīti)."""
    results = list(results)
    return {
        "modules": len(results),
        "pieces": sum(r.total_pieces for r in results),
        "volume_m3": round(sum(r.total_volume_mm3 for r in results) / 1e9, 6),
        "needs_review": sum(1 for r in results if r.needs_review),
        "regular": sum(r.regular_count for r in results),
        "replaced": sum(r.replaced_count for r in results),
        "added": sum(r.added_count for r in results),
        "modules_with_reinforcements": sum(1 for r in results if r.reinforcements),
    }


def _csv_safe(text):
    """Aizsardzība pret formulu injekciju Excel (=, +, -, @ sākumā)."""
    text = str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


EXPORT_HEADER = ["Modulis", "Elements", "b_mm", "h_mm", "L_mm", "Gab", "Apjoms_m3",
                 "Pamatojums", "Atlikums_mm", "Japarbauda", "Avots",
                 "Ass_no_gala_mm", "Pastiprinajuma_avots", "Apjoma_robeza"]


def export_rows(results) -> list:
    """CSV rindas (ar galveni): moduļu rindas, katrs 150×240 pastiprinājums ATSEVIŠĶI (ar asi un apstiprinājuma avotu),
    un KOPĀ rinda ar skaidru apjoma robežu."""
    results = list(results)
    rows = [EXPORT_HEADER]
    for r in results:
        common_tail = [r.remainder_mm, "JĀ" if r.needs_review else "", _csv_safe(r.source)]
        for beam in r.rows:
            if beam.element in (ELEMENT_RF_REPLACE, ELEMENT_RF_ADD):
                mode = "replace" if beam.element == ELEMENT_RF_REPLACE else "add"
                for pl in (x for x in r.reinforcements if x.mode == mode):          # katrs pastiprinājums atsevišķi
                    label = (f"{beam.element}, {pl.label}"
                             + (f", aizvieto regulāro Nr. {pl.replaces}" if pl.replaces else ""))
                    rows.append([_csv_safe(r.name), label, beam.width_mm, beam.height_mm, beam.length_mm, 1,
                                 f"{round(beam.width_mm * beam.height_mm * beam.length_mm / 1e9, 6):.6f}", beam.basis, *common_tail,
                                 format_axis(pl.axis), _csv_safe(r.reinforcement_source), r.volume_scope])
                continue
            rows.append([_csv_safe(r.name), beam.element, beam.width_mm, beam.height_mm, beam.length_mm, beam.count,
                         f"{beam.volume_m3:.6f}", beam.basis, *common_tail, "", "", r.volume_scope])
    total = summarize_modules(results)
    reinforced = total["modules_with_reinforcements"] > 0
    rows.append(["KOPĀ (pamatrāmis + lietotāja pastiprinājumi)" if reinforced else "KOPĀ (tikai pamatrāmis)",
                 "", "", "", "", total["pieces"], f"{total['volume_m3']:.6f}",
                 "Provizorisks; nav konstruktora specifikācija", "", "JĀ" if total["needs_review"] else "", "",
                 "", "", VOLUME_SCOPE_REINFORCED if reinforced else VOLUME_SCOPE_BASE])
    return rows
