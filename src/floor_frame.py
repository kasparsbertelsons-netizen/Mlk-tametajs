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
from dataclasses import dataclass, field
from numbers import Integral, Real
from math import isfinite

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
    cross_positions: tuple          # ((sākums, beigas), …) mm no moduļa gala
    warnings: tuple = field(default_factory=tuple)

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
            return (f"Perimetra sija {self.params.perimeter_width_mm}×"
                    f"{self.params.beam_height_mm} mm ir NOKLUSĒJUMS, nav nolasīts no rasējuma.",)
        return ("Izmantoti lietotāja apstiprināti nestandarta parametri.",)


@dataclass(frozen=True)
class ModuleSpec:
    length_mm: object
    width_mm: object
    name: str = "Modulis"
    source: str = "Ievadīts manuāli"
    params: FrameParams = DEFAULT_PARAMS
    nonstandard_confirmed: bool = False


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
                     params=DEFAULT_PARAMS, nonstandard_confirmed=False) -> ModuleResult:
    """Viena taisnstūra moduļa pamatrāmis no APSTIPRINĀTIEM L un W (mm).

    Izmet ValueError nederīgiem izmēriem un nestandarta parametriem bez apstiprinājuma.
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

    basis = "Noklusējums" if is_default else "Apstiprināti nestandarta parametri"
    rows = (
        BeamRow(ELEMENT_LONG, p, params.beam_height_mm, length, 2, f"{basis}: visā garumā L"),
        BeamRow(ELEMENT_END, p, params.beam_height_mm, span, 2, f"{basis}: W − 2 × perimetrs"),
        BeamRow(ELEMENT_CROSS, cross_w, params.beam_height_mm, span, count,
                f"{basis}: {gap} mm brīva atstarpe, {pitch} mm solis; atlikums bez pārdalīšanas"),
    )

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

    result = ModuleResult(
        name=name, source=source, length_mm=length, width_mm=width, params=params,
        params_default=is_default, clear_length_mm=clear, cross_count=count,
        remainder_mm=remainder, rows=rows, cross_positions=positions, warnings=tuple(warnings))
    problems = layout_problems(result)
    if problems:  # iekšēja pretruna = kļūda kodā, nevis lietotāja datos
        raise RuntimeError("Siju novietojuma pārbaude neizdevās: " + "; ".join(problems))
    return result


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
                params=spec.params, nonstandard_confirmed=spec.nonstandard_confirmed))
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
    }


def _csv_safe(text):
    """Aizsardzība pret formulu injekciju Excel (=, +, -, @ sākumā)."""
    text = str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


EXPORT_HEADER = ["Modulis", "Elements", "b_mm", "h_mm", "L_mm", "Gab", "Apjoms_m3",
                 "Pamatojums", "Atlikums_mm", "Japarbauda", "Avots"]


def export_rows(results) -> list:
    """CSV rindas (ar galveni) visiem moduļiem un KOPĀ rindu."""
    results = list(results)
    rows = [EXPORT_HEADER]
    for r in results:
        for beam in r.rows:
            rows.append([_csv_safe(r.name), beam.element, beam.width_mm, beam.height_mm,
                         beam.length_mm, beam.count, f"{beam.volume_m3:.6f}", beam.basis,
                         r.remainder_mm, "JĀ" if r.needs_review else "", _csv_safe(r.source)])
    total = summarize_modules(results)
    rows.append(["KOPĀ (tikai pamatrāmis)", "", "", "", "", total["pieces"],
                 f"{total['volume_m3']:.6f}", "Provizorisks; nav konstruktora specifikācija",
                 "", "JĀ" if total["needs_review"] else "", ""])
    return rows
