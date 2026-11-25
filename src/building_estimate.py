"""Pilnas ēkas PROVIZORISKĀ materiālu tāme (Issue #12, MVP).

Vienota arhitektūra (Issue #12 + ChatGPT komentāri): KOPĪGA projekta ģeometrija → konstrukciju receptes (CLT — pamata; koka karkass —
2. posms, esošais kods saglabāts) → vienots BOM (materiālu saraksts: artikuls, specifikācija, vienība, neto, rezerve, pasūtāmais,
cena, modulis, konstrukciju grupa, ražošanas posms) → budžeta kopsavilkums → CSV. Ražošanas posmu klasifikācija NAV izstrādāta:
`stage` ir brīvs lietotāja lauks. Patēriņa normas (skrūves, lentes, caurules u.c.) ir lietotāja rediģējamas receptes; MLK normas
un specifikācijas netiek izdomātas.

Tīrs modulis (bez Streamlit/PDF). Visi ievaddati ir LIETOTĀJA ievadīti un apstiprināmi; nekas netiek nolasīts no PDF
un netiek izdomāti trūkstoši izmēri: nezināms lielums = None → rinda ar statusu "nav ievadīts" un brīdinājums.
Grīdas rāmis tiek ņemts no esošā kodola (`src/floor_frame.py`) BEZ izmaiņām.

NAV MLK recepšu, cenu vai normstundu: noklusējuma slāņu saraksts satur tikai nosaukumus; biezumi/soļi paliek tukši, kamēr
tos neievada lietotājs. Rezultāts ir provizorisks materiālu apjoms, nevis gala piedāvājums vai konstruktora specifikācija.

Mērvienības netiek apvienotas: katrai rindai sava vienība (m², m³, m, gab.); kopsavilkums ir pa grupām UN vienībām.
"""
import math
from dataclasses import dataclass, field
from fractions import Fraction

from src.floor_frame import calculate_module
from src.reinforcement import ReinforcementError, parse_axis

G_FLOOR, G_EXT, G_INT = "Grīda", "Ārsienas", "Iekšsienas"
G_ROOF, G_OPEN, G_FINISH = "Jumts", "Logi un durvis", "Iekšējā apdare"
G_FASTEN, G_VENT = "Stiprinājumi un palīgmateriāli", "Ventilācija"
G_ELEC, G_PLUMB = "Elektroinstalācija", "Ūdens un kanalizācija"
G_SANIT, G_EQUIP = "Sanitārtehnika", "Iekārtas un kondicionēšana"
G_TERRACE, G_MANUAL = "Terases (ārpus iekštelpu platības)", "Manuālās rindas"
GROUPS = [G_FLOOR, G_EXT, G_INT, G_ROOF, G_OPEN, G_FINISH, G_FASTEN, G_VENT, G_ELEC, G_PLUMB, G_SANIT, G_EQUIP, G_TERRACE, G_MANUAL]
LAYER_GROUPS = [G_FLOOR, G_EXT, G_INT, G_ROOF, G_FINISH]
MANUAL_GROUPS = [g for g in GROUPS if g != G_TERRACE]
# Obligātās BOM grupas: grupa bez neviena ieraksta tiek rādīta kā «NAV IEVADĪTS» (nezināms nav nulle)
MANDATORY_GROUPS = [G_FLOOR, G_EXT, G_INT, G_ROOF, G_OPEN, G_FINISH, G_FASTEN, G_VENT, G_ELEC, G_PLUMB, G_SANIT, G_EQUIP]

CONSTRUCTIONS = {"clt": "CLT moduļu māja (pamata)", "frame": "Koka karkass (2. posms)"}
STAGE_NOTE = ("AD budžeta stadija: provizorisks apjoms. Tas atšķiras no PD/MEP un apstiprinātu recepšu iepirkumu stadijas; "
              "nepārbaudīts saraksts nav gatavs iepirkšanai.")

ST_OK = "ievadīts"
ST_MISSING = "nav ievadīts"
ST_MANUAL = "manuāli"
ST_ASSUMED = "pieņēmums (nav apstiprināts)"
ST_DUP = "izslēgts (dublikāts)"
ST_UNAPPROVED = "ievadīts (nav apstiprināts)"

DEFAULT_WALL_HEIGHT_MM = 2700            # orientējošs, rediģējams
DEFAULT_WASTE_PCT = 10.0                 # rezerve materiāliem; rediģējama, nošķirta no neto
DEFAULT_PIR_MM = 200                     # Issue #12: PIR 200 mm brīvajās zonās (rediģējams)
OPENING_EXTRA_STUDS = 2                  # pieņēmums: 2 papildu statņi uz atveri (+ 2 sija/palodze = atveres platums)
MAX_ROWS = 200
MAX_MODULES = 10

BASES = {
    "floor_net": "Neto grīdas platība (ievadīta)",
    "floor_frame": "Grīdas rāmja laukums (moduļi Σ L×W)",
    "pir_free": "PIR brīvo zonu laukums (rāmja kodols)",
    "ext_net": "Ārsienu neto laukums (ārpuse, bez atverēm)",
    "ext_inner": "Ārsienu neto laukums (iekšpuse, bez atverēm)",
    "int_one": "Iekšsienu neto laukums (viena puse)",
    "int_both": "Iekšsienu neto laukums (abas puses)",
    "ceiling": "Griestu platība (ievadīta)",
    "roof": "Jumta seguma platība",
}
UNITS = ["m²", "m³", "m"]               # m³ = laukums × biezums; m = laukums / solis (piem. latojums)


def default_layers(construction="clt"):
    """Tikai nosaukumi un bāze; biezumi un soļi NAV izdomāti (statuss 'nav ievadīts', ja vienība to prasa).
    CLT un karkasa slāņu saraksti ir ATŠĶIRĪGI: karkasa recepte netiek uzskatīta par CLT recepti."""
    def layer(group, name, basis, unit="m²", thickness=None, step=None, source=""):
        return {"group": group, "name": name, "basis": basis, "unit": unit, "thickness_mm": thickness,
                "step_mm": step, "waste_pct": DEFAULT_WASTE_PCT, "source": source, "enabled": True, "approved": False,
                "article": None}
    common_top = [layer(G_FLOOR, "Grīdas apdare", "floor_net")]
    common_bottom = [layer(G_ROOF, "Membrāna", "roof"), layer(G_ROOF, "Latojums", "roof", "m"),
                     layer(G_ROOF, "Jumta segums", "roof"), layer(G_FINISH, "Griestu apdare", "ceiling")]
    if construction == "frame":
        return ([layer(G_FLOOR, "Grīdas plātne", "floor_frame")] + common_top + [
            layer(G_EXT, "Fasādes apdare", "ext_net"), layer(G_EXT, "Fasādes latojums", "ext_net", "m"),
            layer(G_EXT, "Vēja plēve", "ext_net"), layer(G_EXT, "Karkasa pildījums (vate)", "ext_net", "m³"),
            layer(G_EXT, "Tvaika plēve", "ext_net"),
            layer(G_EXT, "Instalāciju slānis 50 mm", "ext_net", "m³", 50, None, "Issue #12: 50 mm"),
            layer(G_EXT, "Iekšējā apdare (Fermacell/flīzes/apdares dēlis)", "ext_inner"),
            layer(G_INT, "Karkasa pildījums (vate)", "int_one", "m³"), layer(G_INT, "Apdare abās pusēs", "int_both"),
            layer(G_ROOF, "Jumta siltinājums", "roof", "m³")] + common_bottom)
    return (common_top + [
        layer(G_EXT, "Fasādes apdare", "ext_net"), layer(G_EXT, "Fasādes latojums", "ext_net", "m"),
        layer(G_EXT, "Vēja membrāna", "ext_net"), layer(G_EXT, "Ārsienu siltinājums (pie CLT)", "ext_net", "m³"),
        layer(G_EXT, "Instalāciju slānis", "ext_inner", "m³"),
        layer(G_EXT, "Iekšējā apdare", "ext_inner"),
        layer(G_INT, "Iekšsienu apdare abās pusēs", "int_both"),
        layer(G_ROOF, "Jumta siltinājums", "roof", "m³")] + common_bottom)


def default_clt():
    """CLT paneļu iestatījumi: biezumu NEizdomā — ievada lietotājs un apstiprina. Cena tiek piesaistīta TIKAI izvēlētajai vienībai."""
    def panel(enabled):
        return {"enabled": enabled, "thickness_mm": None, "thickness_confirmed": False, "price_unit": "m²",
                "waste_pct": DEFAULT_WASTE_PCT, "article": None, "source": ""}
    return {"ext": panel(True), "int": panel(True), "roof": panel(False), "floor": panel(False)}


def default_other_costs():
    """Citas izmaksas (EUR): sākumā NAV ievadītas = nav iekļautas (nezināms nav nulle)."""
    return [{"name": n, "amount_eur": None} for n in
            ("MEP darbs un montāža", "Transports", "Montāža objektā", "Pieskaitāmās izmaksas", "Atlīdzība/peļņa")]


def empty_project(name="Jauns projekts", construction="clt"):
    return {
        "name": name, "construction": construction if construction in CONSTRUCTIONS else "clt",
        "floor_frame_enabled": True, "clt": default_clt(), "catalog": [], "recipes": [],
        "other_costs": default_other_costs(), "review": {"reviewer": "", "confirmed": False},
        "modules": [], "floor_net_m2": None, "ceiling_m2": None, "terraces": [],
        "wall_height_mm": DEFAULT_WALL_HEIGHT_MM, "ext_walls": [], "int_walls": [], "openings": [],
        "frames": {k: {"b_mm": None, "h_mm": None, "step_mm": None} for k in ("ext", "int", "roof")},
        "pir": {"enabled": True, "thickness_mm": DEFAULT_PIR_MM},
        "roof": {"mode": "area", "area_m2": None, "footprint_m2": None, "angle_deg": None, "slope_confirmed": False},
        "layers": default_layers(construction), "manual": [], "prices": {}, "waste_default_pct": DEFAULT_WASTE_PCT,
        "excluded": ["Darbs, transports, montāža (ja nav ievadīti sadaļā «Citas izmaksas»)",
                     "Detalizētas inženiertīklu un stiprinājumu receptes (nākamie posmi)"],
    }


# --- recepšu piedziņas lielumi (patēriņa normas) ---------------------------------------------------------------
DRIVERS = {
    "direct": "Tiešs daudzums (manuāli)",
    "ext_net": "m² ārsienu neto", "int_one": "m² iekšsienu neto (viena puse)", "int_both": "m² iekšsienu neto (abas puses)",
    "roof": "m² jumts", "floor_net": "m² grīda neto", "floor_frame": "m² moduļu grīdas laukums", "ceiling": "m² griesti",
    "ext_len": "m ārsienu garums", "int_len": "m iekšsienu garums",
    "win": "gab. logi", "door": "gab. durvis", "modules": "gab. moduļi",
}


# --- palīgfunkcijas ----------------------------------------------------------------------------------------
def num(value):
    """None, ja tukšs/NaN/nav skaitlis; citādi float. Negatīvas vērtības atgriež kā ValueError."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"nederīga vērtība «{str(value)[:20]}»") from None
    if math.isnan(out):
        return None
    if math.isinf(out) or out < 0:
        raise ValueError(f"vērtībai jābūt nenegatīvam skaitlim (ievadīts {value})")
    return out


def parse_axes_text(text):
    """Pastiprinājumu asis (Issue #10): atdalītāji — semikols, atstarpe vai jauna rinda; komats ir decimālzīme."""
    tokens = [t for t in str(text or "").replace(";", " ").split() if t]
    return [parse_axis(t) for t in tokens]


def module_fp(module) -> str:
    """Moduļa apstiprinājuma pirkstu nospiedums: mainoties L, W vai pastiprinājumu asīm, apstiprinājums neder."""
    return f"{module.get('length_mm')}|{module.get('width_mm')}|{' '.join(str(module.get('axes') or '').split())}"


def norm_name(text):
    return " ".join(str(text or "").lower().split())


@dataclass
class Row:
    group: str
    material: str
    qty: object                  # neto daudzums (float) vai None
    unit: str
    basis: str                   # aprēķina pamats (teksts)
    source: str                  # avots / pieņēmums
    status: str
    waste_pct: object = None
    order_qty: object = None
    unit_price: object = None
    hours: object = None
    note: str = ""
    timber: bool = False         # koksnes rinda (kokmateriāla kopsavilkumam)
    # --- BOM lauki (Issue #12, ChatGPT arhitektūras komentārs) ---
    article: object = None       # artikuls (MLK/Moneo sasaiste vēlāk; šajā posmā tikai teksts)
    spec: str = ""               # specifikācija
    module: str = ""             # modulis / telpa / sistēma (brīvs lauks)
    stage: str = ""              # ražošanas posms — klasifikācija NAV izstrādāta; lietotājs ievada vēlāk
    pack_size: object = None     # iepakojums (ja zināms): pasūtāmais tiek noapaļots uz augšu līdz iepakojumam
    approved: object = None      # True/False — lietotāja apstiprinājums; None — atvasināts no ģeometrijas
    alt_qty: object = None       # alternatīvā vienība (piem., CLT m³, ja cena pēc m²); NEKAD netiek cenota
    alt_unit: str = ""
    vol_net: object = None       # koksnes apjoms m³ (neto) kopsavilkumam
    vol_order: object = None

    @property
    def cost(self):
        return None if self.unit_price is None or self.order_qty is None else self.order_qty * self.unit_price

    def price_key(self):
        return f"{self.group}|{self.material}"

    @property
    def approval(self):
        return "—" if self.approved is None else ("apstiprināts" if self.approved else "nav apstiprināts")


@dataclass
class Estimate:
    rows: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)          # bloķē attiecīgo sadaļu (rādītas lietotājam)
    missing: dict = field(default_factory=dict)         # grupa → [kas trūkst]
    areas: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)          # (nosaukums, vērtība, ok)
    modules: list = field(default_factory=list)         # ModuleResult
    excluded: list = field(default_factory=list)
    construction: str = "clt"
    other_costs: list = field(default_factory=list)     # [(nosaukums, EUR vai None)]
    review: dict = field(default_factory=dict)          # atbildīgās personas pārbaude

    def group_status(self, group):
        if self.missing.get(group) or any(e.startswith(group) for e in self.errors):
            return "NEPILNA"
        rows = [r for r in self.rows if r.group == group and r.status != ST_DUP]
        if not rows:
            return "NAV IEVADĪTS" if group in MANDATORY_GROUPS else "nav ievadīta"
        if all(r.status == ST_MANUAL for r in rows):
            return "tikai manuāla"
        return "ievadīta"

    @property
    def complete(self):
        """Visas pamatgrupas ievadītas (grīda, ārsienas, jumts) un nav trūkstošu ievaddatu/kļūdu."""
        return (not self.errors and not any(self.missing.values())
                and all(any(r.group == g for r in self.rows) for g in (G_FLOOR, G_EXT, G_ROOF)))

    @property
    def uncovered(self):
        """Obligātās BOM grupas bez neviena ieraksta (nezināms nav nulle: tās NAV «iekļautas ar 0»)."""
        return [g for g in MANDATORY_GROUPS if not any(r.group == g and r.status != ST_DUP for r in self.rows)]

    def budget(self):
        """Budžeta kopsavilkums: tikai IEVADĪTĀS cenas un citas izmaksas; nepilnība tiek skaidri norādīta."""
        priced = [r for r in self.rows if r.cost is not None]
        unpriced = [r for r in self.rows if r.qty is not None and r.cost is None and r.status != ST_DUP]
        materials = sum(r.cost for r in priced)
        entered = [(n, a) for n, a in self.other_costs if a is not None]
        absent = [n for n, a in self.other_costs if a is None]
        other = sum(a for _n, a in entered)
        hours = [r.hours for r in self.rows if r.hours is not None]
        return {"materials": materials, "priced_rows": len(priced), "unpriced_rows": len(unpriced), "other": other,
                "other_entered": entered, "other_missing": absent, "total": materials + other,
                "hours": sum(hours) if hours else None,
                "unapproved_rows": sum(1 for r in self.rows if r.approved is False and r.qty is not None),
                "incomplete": bool(unpriced or absent or self.uncovered or self.missing or self.errors)}

    @property
    def procurement_status(self):
        """Gatavu iepirkumu sarakstu nosaka atbildīgās personas pārbaude UN obligāto grupu pārklājums (ChatGPT)."""
        who = str((self.review or {}).get("reviewer") or "").strip()
        if not ((self.review or {}).get("confirmed") and who):
            return "NAV GATAVS IEPIRKUMAM — nav atbildīgās personas pārbaudes"
        if not self.complete or self.uncovered:
            return "NAV GATAVS IEPIRKUMAM — nepilns pārklājums (trūkst datu vai obligāto grupu)"
        return f"Atbildīgās personas ({who}) atzīmēts kā pārbaudīts; apjomi joprojām ir AD stadijas provizoriski"

    def summary(self):
        """Kopsavilkums pa grupām. Dažādu materiālu daudzumi NETIEK summēti (m² dažādiem slāņiem nav jēgas);
        summē tikai koksni (m³), izmaksas (tikai rindām ar ievadītu cenu) un darba stundas (tikai ievadītās)."""
        out = []
        for group in GROUPS:
            rows = [r for r in self.rows if r.group == group and r.status != ST_DUP]
            if not rows and not self.missing.get(group) and group not in MANDATORY_GROUPS:
                continue
            priced = [r for r in rows if r.cost is not None]
            timber = [r for r in rows if r.timber and r.qty is not None]
            out.append({
                "group": group, "status": self.group_status(group), "rows": len(rows),
                "not_entered": sum(1 for r in rows if r.qty is None) + len(self.missing.get(group, [])),
                "timber_net": sum(r.vol_net for r in timber), "timber_order": sum(r.vol_order for r in timber),
                "cost": sum(r.cost for r in priced) if priced else None, "priced_rows": len(priced),
                "unpriced_rows": sum(1 for r in rows if r.qty is not None and r.cost is None),
                "hours": sum(r.hours for r in rows if r.hours is not None) if any(r.hours is not None for r in rows) else None})
        return out


# --- galvenais aprēķins ---------------------------------------------------------------------------------------
def estimate(project: dict) -> Estimate:
    construction = project.get("construction") if project.get("construction") in CONSTRUCTIONS else "frame"
    est = Estimate(excluded=[str(x) for x in project.get("excluded", []) if str(x).strip()], construction=construction,
                   review=dict(project.get("review") or {}))
    waste_default = _safe(est, "Projekts", lambda: num(project.get("waste_default_pct")), DEFAULT_WASTE_PCT)
    if waste_default is None:
        waste_default = DEFAULT_WASTE_PCT

    def missing(group, text):
        est.missing.setdefault(group, []).append(text)

    def add(group, material, qty, unit, basis, source, status=ST_OK, waste=None, note="", pieces=False, timber=False, **extra):
        order = None
        pack = extra.get("pack_size")
        if qty is not None:
            w = 0.0 if waste is None else waste
            order = qty * (1 + w / 100.0)
            if pieces:
                order = math.ceil(round(order, 9))
            if pack:
                order = math.ceil(round(order / pack, 9)) * pack          # iepakojuma noapaļošana (tikai ja iepakojums zināms)
        row = Row(group, material, qty, unit, basis, source, status, waste, order, note=note, timber=timber, **extra)
        if timber and qty is not None and row.vol_net is None and unit == "m³":
            row.vol_net, row.vol_order = qty, order
        est.rows.append(row)

    prices = project.get("prices") or {}
    areas = est.areas

    # ---------------- grīda (esošais rāmja kodols) ----------------
    modules = project.get("modules") or []
    if len(modules) > MAX_MODULES:
        est.errors.append(f"{G_FLOOR}: pārāk daudz moduļu (maks. {MAX_MODULES}).")
        modules = modules[:MAX_MODULES]
    frame_area = free_area = 0.0
    floor_frame_on = project.get("floor_frame_enabled", True)       # CLT projektā koka pamatrāmis nav obligāts
    confirmed = 0
    perimeters = Fraction(0)
    for i, m in enumerate(modules, 1):
        name = str(m.get("name") or f"Modulis {i}").strip()[:60] or f"Modulis {i}"
        if not m.get("confirmed"):
            missing(G_FLOOR, f"{name}: L/W nav apstiprināti — modulis netiek skaitīts")
            continue
        try:
            length, width = num(m.get("length_mm")), num(m.get("width_mm"))
            if not length or not width:
                missing(G_FLOOR, f"{name}: L un W nav ievadīti")
                continue
            axes = parse_axes_text(m.get("axes"))
            res = calculate_module(int(length), int(width), name=name, source="Lietotāja apstiprināts (pilnas ēkas tāme)",
                                   reinforcements=axes)
        except (ValueError, ReinforcementError) as error:
            est.errors.append(f"{G_FLOOR}: {name}: {error}")
            continue
        confirmed += 1
        est.modules.append(res)
        perimeters += 2 * (res.length_mm + res.width_mm)
        frame_area += res.length_mm * res.width_mm / 1e6
        free_area += float(sum(g.size for g in res.gaps)) * (res.width_mm - 2 * res.params.perimeter_width_mm) / 1e6
        pcs = f"{res.total_pieces} gab.; " + ", ".join(f"{r.element} {r.count}" for r in res.rows)
        if floor_frame_on:
            add(G_FLOOR, f"Grīdas rāmja kokmateriāls — {name}", res.total_volume_m3, "m³",
                f"Esošais rāmja kodols: L {res.length_mm} × W {res.width_mm} mm", res.reinforcement_source if res.reinforcements
                else "Pamatrāmis (apstiprināti L/W)", ST_OK, waste_default, note=pcs, timber=True, module=name)
        for w in res.warnings:
            est.warnings.append(f"{name}: {w.message}")
    areas["modules_confirmed"] = confirmed
    areas["floor_frame_m2"] = round(frame_area, 6)
    areas["pir_free_m2"] = round(free_area, 6)
    areas["module_perimeters_m"] = float(perimeters) / 1000.0
    if not modules:
        missing(G_FLOOR, "nav ievadīts neviens modulis")
    pir = project.get("pir") or {}
    if confirmed and floor_frame_on and pir.get("enabled", True):
        t = _safe(est, f"{G_FLOOR}: PIR", lambda: num(pir.get("thickness_mm")), None)
        if t:
            add(G_FLOOR, f"PIR siltinājums {t:g} mm brīvajās zonās starp sijām", free_area, "m²",
                f"Σ brīvās atstarpes × (W − 2 × perimetra platums); m³ = {free_area * t / 1000:.3f}", "Rāmja kodola atstarpes; biezums lietotāja",
                ST_OK, waste_default)
        else:
            missing(G_FLOOR, "PIR biezums nav ievadīts")

    floor_net = _safe(est, "Platības", lambda: num(project.get("floor_net_m2")), None)
    ceiling = _safe(est, "Platības", lambda: num(project.get("ceiling_m2")), None)
    areas["floor_net_m2"], areas["ceiling_m2"] = floor_net, ceiling
    if floor_net is None:
        missing(G_FLOOR, "neto grīdas platība nav ievadīta (grīdas apdare netiek skaitīta)")
    elif confirmed and floor_net > frame_area + 1e-9:
        est.warnings.append(f"Neto grīdas platība {floor_net:g} m² pārsniedz moduļu laukumu {frame_area:g} m²: pārbaudi ievadi.")

    # ---------------- atveres ----------------
    open_area = {"Ārsiena": 0.0, "Iekšsiena": 0.0}
    open_rows = []
    for i, o in enumerate(project.get("openings") or [], 1):
        label = str(o.get("name") or f"Atvere {i}").strip()
        try:
            w, h, cnt = num(o.get("width_mm")), num(o.get("height_mm")), num(o.get("count"))
        except ValueError as error:
            est.errors.append(f"{G_OPEN}: {label}: {error}")
            continue
        wall = o.get("wall") if o.get("wall") in open_area else "Ārsiena"
        if not (w and h and cnt):
            missing(G_OPEN, f"{label}: platums, augstums un skaits jāievada")
            continue
        if cnt != int(cnt):
            est.errors.append(f"{G_OPEN}: {label}: skaitam jābūt veselam.")
            continue
        open_area[wall] += w * h * cnt / 1e6
        open_rows.append((o.get("kind") or "Logs", label, int(w), int(h), int(cnt), wall))
    for kind, label, w, h, cnt, wall in open_rows:
        add(G_OPEN, f"{kind}: {label} {w}×{h} mm ({wall.lower()})", cnt, "gab.", f"{cnt} × {w}×{h} mm = {cnt * w * h / 1e6:.3f} m²",
            "Lietotāja ievade", ST_OK, 0.0, pieces=True)
    areas["openings_ext_m2"], areas["openings_int_m2"] = round(open_area["Ārsiena"], 6), round(open_area["Iekšsiena"], 6)
    ext_open_count = sum(c for _k, _l, _w, _h, c, wall in open_rows if wall == "Ārsiena")
    int_open_count = sum(c for _k, _l, _w, _h, c, wall in open_rows if wall == "Iekšsiena")

    # ---------------- sienas ----------------
    default_h = _safe(est, "Sienas", lambda: num(project.get("wall_height_mm")), None)
    wall_data = {}
    for key, group, label in (("ext_walls", G_EXT, "ārsiena"), ("int_walls", G_INT, "iekšsiena")):
        total_len = gross = 0.0
        segs = []
        for i, s in enumerate(project.get(key) or [], 1):
            sname = str(s.get("name") or f"{label} {i}").strip()
            try:
                length, h = num(s.get("length_m")), num(s.get("height_mm"))
            except ValueError as error:
                est.errors.append(f"{group}: {sname}: {error}")
                continue
            h = h if h else default_h
            if not length:
                missing(group, f"{sname}: garums nav ievadīts")
                continue
            if not h:
                missing(group, f"{sname}: augstums nav ievadīts")
                continue
            total_len += length
            gross += length * h / 1000.0
            segs.append((sname, length, h))
        opening = open_area["Ārsiena" if key == "ext_walls" else "Iekšsiena"]
        net = gross - opening
        if segs and net <= 0:
            est.errors.append(f"{group}: atveru laukums ({opening:g} m²) nav mazāks par sienu bruto laukumu ({gross:g} m²).")
            net = None
        if not segs:
            missing(group, "nav ievadīts neviens sienas posms")
            net = None
        wall_data[key] = (segs, total_len, gross, net)
        areas[f"{key}_length_m"], areas[f"{key}_gross_m2"] = round(total_len, 6), round(gross, 6)
        areas[f"{key}_net_m2"] = None if net is None else round(net, 6)
    ext_net = wall_data["ext_walls"][3]
    int_net = wall_data["int_walls"][3]
    # kopīgās moduļu šuves nedrīkst automātiski skaitīties kā fasāde: kontrole pret moduļu perimetru
    ext_len = wall_data["ext_walls"][1]
    if confirmed and ext_len:
        per = areas["module_perimeters_m"]
        if ext_len > per + 1e-9:
            est.errors.append(f"{G_EXT}: ārsienu garums {ext_len:g} m pārsniedz moduļu perimetru {per:g} m — nav iespējams.")
        elif confirmed > 1 and ext_len >= per - 1e-9:
            est.warnings.append(f"Ārsienu garums {ext_len:g} m = visu moduļu perimetrs: iespējams, kopīgās moduļu šuves ir "
                                "uzskaitītas kā fasāde. Pārbaudi (šuves jāizslēdz).")
    areas["ext_inner_m2"] = areas["ext_walls_net_m2"]
    areas["int_both_m2"] = None if int_net is None else round(2 * int_net, 6)
    areas["int_one_m2"] = None if int_net is None else round(int_net, 6)

    # ---------------- jumts ----------------
    roof = project.get("roof") or {}
    roof_area = None
    try:
        if roof.get("mode") == "slope":
            fp, ang = num(roof.get("footprint_m2")), num(roof.get("angle_deg"))
            if not fp or not ang:
                missing(G_ROOF, "slīpuma aprēķinam jāievada jumta projekcijas laukums un leņķis")
            elif not 0 <= ang < 80:
                est.errors.append(f"{G_ROOF}: slīpuma leņķim jābūt 0–80°.")
            elif not roof.get("slope_confirmed"):
                missing(G_ROOF, "slīpuma aprēķins nav apstiprināts (atzīmē apstiprinājumu)")
            else:
                roof_area = fp / math.cos(math.radians(ang))
        else:
            roof_area = num(roof.get("area_m2")) or None
            if roof_area is None:
                missing(G_ROOF, "jumta seguma platība nav ievadīta")
    except ValueError as error:
        est.errors.append(f"{G_ROOF}: {error}")
    areas["roof_m2"] = None if roof_area is None else round(roof_area, 6)

    basis_value = {"floor_net": floor_net, "floor_frame": frame_area if confirmed else None,
                   "pir_free": free_area if confirmed else None, "ext_net": ext_net, "ext_inner": ext_net,
                   "int_one": int_net, "int_both": None if int_net is None else 2 * int_net,
                   "ceiling": ceiling, "roof": roof_area}

    # ---------------- karkasa koks (sienas, spāres) ----------------
    frames = project.get("frames") or {}
    frame_walls = (("ext", G_EXT, "Ārsienu"), ("int", G_INT, "Iekšsienu")) if construction == "frame" else ()
    for key, group, title in frame_walls:
        data = wall_data[f"{key}_walls"]
        if not data[0]:
            continue
        p = _frame_params(est, frames.get(key) or {}, group, f"{title} karkasa")
        if p is None:
            missing(group, f"{title} karkasa šķērsgriezums un solis nav ievadīti (karkasa koks netiek skaitīts)")
            continue
        b, h, step = p
        studs = sum(math.ceil(round(length * 1000 / step, 9)) + 1 for _n, length, _h in data[0])
        n_open = ext_open_count if key == "ext" else int_open_count
        extra = OPENING_EXTRA_STUDS * n_open
        stud_m = sum((math.ceil(round(length * 1000 / step, 9)) + 1) * hh / 1000 for _n, length, hh in data[0])
        avg_h = sum(hh for *_x, hh in data[0]) / len(data[0]) / 1000
        stud_m += extra * avg_h
        plates_m = 2 * data[1]
        open_m = 2 * sum(w * c for _k, _l, w, _h, c, wall in open_rows if wall == ("Ārsiena" if key == "ext" else "Iekšsiena")) / 1000
        vol = (stud_m + plates_m + open_m) * b * h / 1e6
        src = "Lietotāja ievadīts šķērsgriezums/solis (nav apstiprināta MLK recepte)"
        basis = f"{b:g}×{h:g} mm, solis {step:g} mm"
        add(group, f"{title} karkasa statņi", studs + extra, "gab.",
            f"⌈garums/solis⌉+1 katram posmam + {OPENING_EXTRA_STUDS} papildu statņi uz atveri ({extra})", src, ST_ASSUMED, waste_default,
            note=basis, pieces=True)
        add(group, f"{title} karkasa laidi (augša/apakša) un atveru sijas", plates_m + open_m, "m",
            "2 × sienu garums + 2 × atveres platums katrai atverei", src, ST_ASSUMED, waste_default, note=basis)
        add(group, f"{title} karkasa kokmateriāls kopā", vol, "m³", f"(statņi + laidi + atveru sijas) × {b:g}×{h:g} mm", src,
            ST_ASSUMED, waste_default, note="Statņi, laidi un atveru sijas apvienoti tikai kā m³ kopsumma", timber=True)
    if roof_area:
        p = _frame_params(est, frames.get("roof") or {}, G_ROOF, "Jumta spāru")
        clt_roof = construction == "clt" and ((project.get("clt") or {}).get("roof") or {}).get("enabled")
        if p is None:
            if construction == "frame":
                missing(G_ROOF, "spāru šķērsgriezums un solis nav ievadīti (spāres netiek skaitītas)")
            elif not clt_roof:
                missing(G_ROOF, "jumta nesošā konstrukcija nav izvēlēta (CLT jumta paneļi vai spāres) — netiek skaitīta")
        else:
            b, h, step = p
            length_m = roof_area * 1000 / step
            add(G_ROOF, "Jumta spāres (provizoriski)", length_m, "m", f"jumta platība / solis ({step:g} mm); {b:g}×{h:g} mm",
                "Lietotāja ievadīts; provizorisks, bez konstrukcijas risinājuma", ST_ASSUMED, waste_default)
            add(G_ROOF, "Jumta spāru kokmateriāls (provizoriski)", length_m * b * h / 1e6, "m³", f"{length_m:.3f} m × {b:g}×{h:g} mm",
                "Lietotāja ievadīts; provizorisks", ST_ASSUMED, waste_default, timber=True)

    # ---------------- CLT paneļi (pamata recepte; Issue #12 ChatGPT komentārs) ----------------
    if construction == "clt":
        clt = project.get("clt") or {}
        floor_panel_area = frame_area if confirmed else None
        for key, group, title, area, what in (
                ("ext", G_EXT, "CLT ārsienu paneļi", ext_net, "ārsienu neto laukums (bez atverēm)"),
                ("int", G_INT, "CLT iekšsienu paneļi", int_net, "iekšsienu neto laukums (viena puse, bez atverēm)"),
                ("roof", G_ROOF, "CLT jumta paneļi", roof_area, "jumta seguma platība"),
                ("floor", G_FLOOR, "CLT grīdas paneļi", floor_panel_area, "moduļu grīdas laukums Σ L×W")):
            cfg = clt.get(key) or {}
            if not cfg.get("enabled"):
                continue
            try:
                t, w = num(cfg.get("thickness_mm")), num(cfg.get("waste_pct"))
            except ValueError as error:
                est.errors.append(f"{group}: {title}: {error}")
                continue
            w = DEFAULT_WASTE_PCT if w is None else w            # CLT rezerve regulējama atsevišķi no pārējās
            unit = cfg.get("price_unit") if cfg.get("price_unit") in ("m²", "m³") else "m²"
            common = dict(article=cfg.get("article"), spec=f"CLT panelis, biezums {t:g} mm" if t else "CLT panelis, biezums nav ievadīts",
                          approved=bool(cfg.get("thickness_confirmed")))
            src = cfg.get("source") or "Lietotāja ievadīts biezums (nav MLK specifikācija)"
            if area is None:
                add(group, title, None, unit, what, src, ST_MISSING, **common)
                continue
            if not t:
                add(group, title, None, unit, f"{what} × biezums", src, ST_MISSING, **common)
                missing(group, f"{title}: paneļa biezums nav ievadīts")
                continue
            vol = area * t / 1000.0
            qty, alt_qty, alt_unit = (area, vol, "m³") if unit == "m²" else (vol, area, "m²")
            add(group, title, qty, unit, f"{what} {area:.3f} m² × {t:g} mm = {vol:.3f} m³; cena TIKAI par {unit}", src,
                ST_OK if cfg.get("thickness_confirmed") else ST_UNAPPROVED, w, timber=True, alt_qty=alt_qty, alt_unit=alt_unit,
                vol_net=vol, vol_order=vol * (1 + w / 100.0),
                note=f"Alternatīvā vienība (netiek cenota): {alt_qty:.3f} {alt_unit}", **common)

    # ---------------- slāņi (vienots mehānisms; dublikātu pārbaude) ----------------
    seen = {}
    for i, layer in enumerate(project.get("layers") or [], 1):
        if layer.get("enabled") is False:
            continue
        group = layer.get("group") if layer.get("group") in LAYER_GROUPS else None
        name = str(layer.get("name") or "").strip()
        basis_key = layer.get("basis")
        if group is None or not name or basis_key not in BASES:
            est.errors.append(f"{G_MANUAL}: slāņa rinda {i} ir nepilnīga (grupa/nosaukums/pamats).")
            continue
        unit = layer.get("unit") if layer.get("unit") in UNITS else "m²"
        try:
            thickness, step, waste = num(layer.get("thickness_mm")), num(layer.get("step_mm")), num(layer.get("waste_pct"))
        except ValueError as error:
            est.errors.append(f"{group}: {name}: {error}")
            continue
        waste = waste_default if waste is None else waste
        dup_key = (norm_name(name), basis_key)
        if dup_key in seen:
            est.warnings.append(f"«{name}» ({BASES[basis_key]}) jau ir ieskaitīts grupā «{seen[dup_key]}»: dublikāts netiek "
                                "skaitīts (viens un tas pats slānis nedrīkst tikt ieskaitīts divreiz).")
            est.rows.append(Row(group, name, None, unit, BASES[basis_key], layer.get("source") or "", ST_DUP,
                                note="Dublikāts"))
            continue
        seen[dup_key] = group
        area = basis_value.get(basis_key)
        source = layer.get("source") or "Lietotāja slānis"
        approved = bool(layer.get("approved"))
        lstatus = ST_OK if approved else ST_UNAPPROVED
        lx = dict(article=layer.get("article") or None, approved=approved)
        if area is None:
            add(group, name, None, unit, BASES[basis_key], source, ST_MISSING, **lx)
            missing(group, f"«{name}»: nav ievadīts pamats «{BASES[basis_key]}»")
            continue
        if unit == "m³":
            if not thickness:
                add(group, name, None, unit, f"{BASES[basis_key]} × biezums", source, ST_MISSING, **lx)
                missing(group, f"«{name}»: biezums nav ievadīts")
                continue
            add(group, name, area * thickness / 1000.0, unit, f"{BASES[basis_key]} {area:.3f} m² × {thickness:g} mm", source,
                lstatus, waste, **lx)
        elif unit == "m":
            if not step:
                add(group, name, None, unit, f"{BASES[basis_key]} / solis", source, ST_MISSING, **lx)
                missing(group, f"«{name}»: solis nav ievadīts")
                continue
            add(group, name, area * 1000.0 / step, unit, f"{BASES[basis_key]} {area:.3f} m² / {step:g} mm", source, lstatus, waste, **lx)
        else:
            add(group, name, area, unit, f"{BASES[basis_key]}", source, lstatus, waste, **lx)

    # ---------------- terases un manuālās rindas ----------------
    for i, t in enumerate(project.get("terraces") or [], 1):
        label = str(t.get("name") or f"Terase {i}").strip()
        try:
            area = num(t.get("area_m2"))
        except ValueError as error:
            est.errors.append(f"{G_TERRACE}: {label}: {error}")
            continue
        if not area:
            missing(G_TERRACE, f"{label}: platība nav ievadīta")
            continue
        add(G_TERRACE, f"Terase: {label}", area, "m²", "Lietotāja ievade; netiek ieskaitīta iekštelpu platībā", "Lietotāja ievade")
    for i, m in enumerate(project.get("manual") or [], 1):
        group = m.get("group") if m.get("group") in MANUAL_GROUPS else G_MANUAL
        material = str(m.get("material") or "").strip()
        unit = str(m.get("unit") or "").strip() or "gab."
        try:
            qty, waste = num(m.get("qty")), num(m.get("waste_pct"))
        except ValueError as error:
            est.errors.append(f"{G_MANUAL}: rinda {i}: {error}")
            continue
        if not material or qty is None:
            est.errors.append(f"{G_MANUAL}: rinda {i}: jānorāda materiāls un daudzums.")
            continue
        pack = _safe(est, f"{G_MANUAL}: rinda {i}", lambda: num(m.get("pack_size")), None)
        add(group, material, qty, unit, "Lietotāja manuāli ievadīts apjoms", str(m.get("source") or "Manuāli")[:120], ST_MANUAL,
            0.0 if waste is None else waste, pieces=(unit == "gab."), article=m.get("article") or None,
            spec=str(m.get("spec") or ""), module=str(m.get("module") or ""), stage=str(m.get("stage") or ""),
            pack_size=pack or None, approved=bool(m.get("approved")))

    # ---------------- receptes ar rediģējamām patēriņa normām (stiprinājumi, lentes, MEP u.c.) ----------------
    catalog = {str(c.get("article")).strip(): c for c in project.get("catalog") or [] if str(c.get("article") or "").strip()}
    n_open = lambda kind: sum(c for k, _l, _w, _h, c, _wall in open_rows if k == kind)
    drivers = {"ext_net": ext_net, "int_one": int_net, "int_both": None if int_net is None else 2 * int_net, "roof": roof_area,
               "floor_net": floor_net, "floor_frame": frame_area if confirmed else None, "ceiling": ceiling,
               "ext_len": wall_data["ext_walls"][1] or None, "int_len": wall_data["int_walls"][1] or None,
               "win": n_open("Logs") or None, "door": n_open("Durvis") or None, "modules": confirmed or None}
    for i, line in enumerate(project.get("recipes") or [], 1):
        if line.get("enabled") is False:
            continue
        art = str(line.get("article") or "").strip() or None
        cat = catalog.get(art) or {}
        name = str(line.get("name") or cat.get("name") or "").strip()
        unit = str(line.get("unit") or cat.get("unit") or "").strip()
        group = line.get("group") if line.get("group") in MANUAL_GROUPS else None
        driver = line.get("driver") if line.get("driver") in DRIVERS else "direct"
        if not name or not unit or group is None:
            est.errors.append(f"{G_MANUAL}: receptes rinda {i} ir nepilnīga (jānorāda grupa, nosaukums/artikuls un mērvienība).")
            continue
        try:
            norm, direct, waste, pack = (num(line.get(k)) for k in ("norm", "qty", "waste_pct", "pack_size"))
        except ValueError as error:
            est.errors.append(f"{group}: «{name}»: {error}")
            continue
        if pack is None:
            pack = _safe(est, f"{group}: «{name}»", lambda: num(cat.get("pack_size")), None)
        waste = waste_default if waste is None else waste
        approved = bool(line.get("approved"))
        extra = dict(article=art, spec=str(line.get("spec") or cat.get("spec") or ""), module=str(line.get("module") or ""),
                     stage=str(line.get("stage") or ""), pack_size=pack or None, approved=approved)
        source = str(line.get("source") or "Lietotāja recepte")[:120]
        status = ST_OK if approved else ST_UNAPPROVED
        if driver == "direct":
            if direct is None:
                add(group, name, None, unit, "Tiešs daudzums", source, ST_MISSING, **extra)
                missing(group, f"«{name}»: daudzums nav ievadīts")
                continue
            add(group, name, direct, unit, "Tiešs lietotāja ievadīts daudzums", source, status, waste, pieces=(unit == "gab."), **extra)
            continue
        value = drivers.get(driver)
        if value is None or norm is None:
            add(group, name, None, unit, f"{DRIVERS[driver]} × patēriņa norma", source, ST_MISSING, **extra)
            missing(group, f"«{name}»: " + ("nav ievadīta patēriņa norma" if norm is None else f"nav pieejams pamats «{DRIVERS[driver]}»"))
            continue
        add(group, name, value * norm, unit, f"{DRIVERS[driver]} {value:g} × norma {norm:g} {unit} uz vienību", source, status,
            waste, pieces=(unit == "gab."), **extra)

    if len(est.rows) > MAX_ROWS:
        est.errors.append(f"Pārāk daudz tāmes rindu (maks. {MAX_ROWS}).")

    # ---------------- cenas un darba stundas (neobligāti, manuāli) ----------------
    for r in est.rows:
        entry = prices.get(r.price_key()) or {}
        try:
            r.unit_price, r.hours = num(entry.get("price")), num(entry.get("hours"))
            cat = catalog.get(r.article) if r.article else None
            if r.unit_price is None and cat is not None and num(cat.get("unit_price")) is not None:
                if str(cat.get("unit") or r.unit).strip() == r.unit:
                    r.unit_price = num(cat.get("unit_price"))          # cena no artikulu kataloga (viena cena visām rindām)
                else:
                    est.warnings.append(f"Katalogs: artikula «{r.article}» cena ir par «{cat.get('unit')}», bet rinda «{r.material}» "
                                        f"ir «{r.unit}»: cena netiek piemērota.")
        except ValueError as error:
            est.errors.append(f"Cenas: {r.material}: {error}")
    for item in project.get("other_costs") or []:
        label = str(item.get("name") or "").strip()
        if not label:
            continue
        try:
            est.other_costs.append((label, num(item.get("amount_eur"))))
        except ValueError as error:
            est.errors.append(f"Citas izmaksas: {label}: {error}")
            est.other_costs.append((label, None))

    _controls(est, areas)
    return est


def _safe(est, where, fn, default):
    try:
        return fn()
    except ValueError as error:
        est.errors.append(f"{where}: {error}")
        return default


def _frame_params(est, p, group, title):
    try:
        b, h, step = num(p.get("b_mm")), num(p.get("h_mm")), num(p.get("step_mm"))
    except ValueError as error:
        est.errors.append(f"{group}: {title}: {error}")
        return None
    return (b, h, step) if b and h and step else None


def _controls(est, a):
    """Neatkarīgi vienkārši kontroles lielumi, kas rādīti lietotājam (nav aizstājums testiem)."""
    def check(name, value, ok=True):
        est.checks.append((name, value, ok))
    if a.get("ext_walls_gross_m2") is not None and a.get("ext_walls_net_m2") is not None:
        check("Ārsienas: bruto − atveres = neto", f"{a['ext_walls_gross_m2']:.3f} − {a['openings_ext_m2']:.3f} = {a['ext_walls_net_m2']:.3f} m²",
              abs(a["ext_walls_gross_m2"] - a["openings_ext_m2"] - a["ext_walls_net_m2"]) < 1e-6)
    if a.get("int_walls_net_m2") is not None:
        check("Iekšsienas: neto abas puses = 2 × neto", f"2 × {a['int_walls_net_m2']:.3f} = {a['int_both_m2']:.3f} m²",
              abs(2 * a["int_walls_net_m2"] - a["int_both_m2"]) < 1e-6)
    if a.get("module_perimeters_m"):
        check("Ārsienu garums ≤ moduļu perimetrs (kopīgās šuves izslēgtas)",
              f"{a.get('ext_walls_length_m', 0):g} m ≤ {a['module_perimeters_m']:g} m",
              a.get("ext_walls_length_m", 0) <= a["module_perimeters_m"] + 1e-9)
    if a.get("roof_m2") is not None:
        check("Jumta seguma platība", f"{a['roof_m2']:.3f} m²")


# --- eksports (BOM + budžets) -----------------------------------------------------------------------------------
EXPORT_HEADER = ["Artikuls", "Materiāls", "Specifikācija", "Mervienība", "Neto", "Rezerve_%", "Pasūtāmais", "Iepakojums",
                 "Vienības_cena_EUR", "Izmaksas_EUR", "Modulis_telpa_sistēma", "Konstrukciju_grupa", "Ražošanas_posms",
                 "Avots_pieņēmums", "Apstiprinājums", "Statuss", "Aprēķina_pamats", "Alternatīvā_vienība_(nav_cenota)",
                 "Darba_stundas", "Piezīme"]
NOT_FINAL = "PROVIZORISKA MATERIĀLU TĀME — NAV GALA PIEDĀVĀJUMS"


def _csv_safe(text):
    text = str(text if text is not None else "")
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _fmt(value, digits=3):
    return "" if value is None else f"{value:.{digits}f}"


def export_rows(project_name, est: Estimate):
    """CSV: brīdinājums, stadija, budžets (nepilnība norādīta), grupu pārklājums, BOM rindas, nepilnās sadaļas, neiekļautie darbi."""
    status = "NEPILNA (trūkst ievaddatu vai ir kļūdas)" if not est.complete else "ievaddati ievadīti (joprojām provizoriska)"
    b = est.budget()
    rows = [[_csv_safe(NOT_FINAL)], [_csv_safe(f"Projekts: {project_name}"), f"Statuss: {status}"],
            [_csv_safe(STAGE_NOTE)], [_csv_safe("Iepirkuma gatavība: " + est.procurement_status)],
            ["Konstrukcija:", CONSTRUCTIONS.get(est.construction, est.construction)], [],
            ["BUDŽETA KOPSAVILKUMS (tikai ievadītās cenas; nepilns, ja norādīts)"],
            ["Materiāli (rindas ar cenu)", _fmt(b["materials"], 2), "EUR", f"rindas ar cenu: {b['priced_rows']}",
             f"BEZ CENAS: {b['unpriced_rows']} rindas"],
            ["Citas izmaksas (ievadītās)", _fmt(b["other"], 2), "EUR"] + [f"{n}: {a:.2f}" for n, a in b["other_entered"]],
            ["Citas izmaksas NAV ievadītas (neiekļautas)", "; ".join(b["other_missing"])],
            ["KOPĀ (" + ("NEPILNS" if b["incomplete"] else "ievadītais") + ")", _fmt(b["total"], 2), "EUR"],
            ["Nav apstiprinātas rindas", b["unapproved_rows"]], [],
            ["GRUPU PĀRKLĀJUMS"]]
    for item in est.summary():
        rows.append([_csv_safe(item["group"]), item["status"], f"rindas: {item['rows']}", f"nav ievadīts: {item['not_entered']}",
                     f"koksne neto m3: {item['timber_net']:.3f}"])
    if est.uncovered:
        rows.append(["Obligātās grupas BEZ ieraksta (NAV IEKĻAUTAS)", "; ".join(est.uncovered)])
    rows += [[], EXPORT_HEADER]
    for r in est.rows:
        alt = "" if r.alt_qty is None else f"{r.alt_qty:.3f} {r.alt_unit}"
        rows.append([_csv_safe(r.article), _csv_safe(r.material), _csv_safe(r.spec), r.unit, _fmt(r.qty),
                     "" if r.waste_pct is None else f"{r.waste_pct:g}", _fmt(r.order_qty),
                     "" if r.pack_size is None else f"{r.pack_size:g}", _fmt(r.unit_price, 2), _fmt(r.cost, 2), _csv_safe(r.module),
                     _csv_safe(r.group), _csv_safe(r.stage), _csv_safe(r.source), r.approval, r.status, _csv_safe(r.basis), alt,
                     _fmt(r.hours, 1), _csv_safe(r.note)])
    for group, items in est.missing.items():
        for item in items:
            rows.append(["", _csv_safe(item), "", "", "", "", "", "", "", "", "", _csv_safe(group), "", "", "", ST_MISSING, "", "", "",
                         "NEPILNA SADAĻA"])
    for work in est.excluded:
        rows.append(["", _csv_safe(work), "", "", "", "", "", "", "", "", "", "Neiekļauts", "", "", "", "NAV IEKĻAUTS", "", "", "", ""])
    return rows
