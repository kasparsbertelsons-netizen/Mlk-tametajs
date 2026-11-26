"""AD arhitektūras PDF → pilnas ēkas tāmes ievaddatu KANDIDĀTI (Issue #16, AD-first).

Arhitektūras (AD) rasējums ir vienīgais projektēšanas dokuments sākotnējā piedāvājuma stadijā. Šis modulis no PDF TEKSTA un VEKTORU
ģeometrijas (esošais `src/ad_vector.py`) izvelk kandidātus: moduļu L/W, telpu un terašu laukumus, telpas augstumu, sienu posmus (garums,
augstums, tips, CLT biezums), zelmiņus (trīsstūra gala sienas), atveres (ārējās/iekšējās/jumta atsevišķi), jumta slīpnes (garums, horizontālā
projekcija, leņķis), konstrukciju tipu apzīmējumus ar slāņu kandidātiem.

Katram kandidātam: lauks (`kind`), lappuse, avots (`vektors`/`teksts`), pārliecība (`augsta`/`vidēja`/`zema`), pierādījums (citāts) un
problēmas. NEKAS netiek ierakstīts tāmē bez lietotāja apstiprinājuma (`apply_candidates`). Nezināms nav nulle: ja lauks nav droši nolasāms, tas
netiek aizpildīts, bet atzīmēts, un lietotājs to ievada manuāli.

Atpazīšana ir balstīta uz TEKSTA KONVENCIJĀM (sk. `docs/AD_BUILDING_IMPORT.md`), kas pārbaudītas tikai uz SINTĒTISKA parauga; reāli AD rasējumi var
atšķirties — atpazīšanas pielaides ir prototipa pielaides. Ārējā fasādes kontūra netiek sajaukta ar pamatrāmi un NETIEK izsecināta nobīde.
Datu apjoma ierobežojumi: ≤ 100 lapas, ≤ 30 MB.
"""
import math
import re
from dataclasses import dataclass, field

import pymupdf

from src.ad_plan import TERRACE_RE, classify_page
from src.ad_vector import CONSISTENT, RECOGNISED, UNCLEAR, analyze_pdf
from src.building_estimate import ensure_ids, module_fp, new_id

MAX_BYTES = 30 * 1024 * 1024
MAX_PAGES = 100
HIGH, MEDIUM, LOW = "augsta", "vidēja", "zema"
NUM = r"\d+(?:[.,]\d+)?"

K_MODULE, K_FACADE, K_ROOM, K_TERRACE, K_FLOOR_NET = "module", "facade_contour", "room", "terrace", "floor_net"
K_CEILING_H, K_WALL, K_GABLE, K_OPENING, K_SLOPE, K_TYPE, K_ROOF_ANGLE = ("ceiling_height", "wall", "gable", "opening", "roof_slope",
                                                                         "construction_type", "roof_angle")
KIND_LABELS = {K_MODULE: "Modulis (L×W)", K_FACADE: "Fasādes kontūra (NAV pamatrāmis)", K_ROOM: "Telpa", K_TERRACE: "Terase",
               K_FLOOR_NET: "Neto grīdas platība", K_CEILING_H: "Telpas augstums", K_WALL: "Sienas posms", K_GABLE: "Zelmiņš",
               K_OPENING: "Atvere", K_SLOPE: "Jumta slīpne", K_TYPE: "Konstrukcijas tips", K_ROOF_ANGLE: "Jumta slīpums (informatīvi)"}

WALL_RE = re.compile(r"^\s*siena\b", re.I)
GABLE_RE = re.compile(r"^\s*zelmi[ņn]š\b", re.I)
SLOPE_RE = re.compile(r"^\s*jumta\s+slīpne\b", re.I)
ROOF_ANGLE_RE = re.compile(r"jumta\s+slīpums\s*[:=]?\s*(" + NUM + r")\s*°", re.I)
CEIL_RE = re.compile(r"(?:telpas|griestu)\s+augstums\s*[:=]?\s*(" + NUM + r")\s*(mm|m)\b", re.I)
ROOM_RE = re.compile(r"^\s*(?P<name>[^\d\n]{3,48}?)\s+(?P<area>" + NUM + r")\s*m\s*[2²]\s*$", re.I)
FLOOR_TOTAL_RE = re.compile(r"neto|kopā|kopsumma|iekštelpu|summa", re.I)
OPENING_RE = re.compile(r"^\s*(?P<code>[A-ZĀČĒĢĪĶĻŅŠŪŽ]{1,3}\d+)\s+(?P<w>\d{3,4})\s*[x×]\s*(?P<h>\d{3,4})\s*(?:mm)?\s+(?P<n>\d+)\s*gab\.?(?P<rest>.*)$")
TAG_RE = re.compile(r"^\s*(?P<code>[A-ZĀČĒĢĪĶĻŅŠŪŽ]{1,3}\d+)\s*$")
TYPE_RE = re.compile(r"^\s*(?P<code>[A-ZĀČĒĢĪĶĻŅŠŪŽ]{1,3}\d+)\s*[-–—:]?\s*(?P<what>Ārsiena|Iekšsiena|Jumts|Grīda)\s*:\s*(?P<layers>.+)$", re.I)
MODULE_TEXT_RE = re.compile(r"(?:pamatrāmis|modulis)\s+(?P<name>\S+)\s+(?P<l>\d{4,5})\s*[x×]\s*(?P<w>\d{3,5})", re.I)
FACADE_TEXT_RE = re.compile(r"(?:fasādes\s+kontūra|ārējais\s+gabarīts)\s+(?P<l>\d{4,5})\s*[x×]\s*(?P<w>\d{3,5})", re.I)
THICK_RE = re.compile(r"(" + NUM + r")\s*mm", re.I)
STEP_RE = re.compile(r"(?:c/c|solis)\s*(\d{2,4})", re.I)
APPLIES = {"ārsiena": "ext", "iekšsiena": "int", "jumts": "roof", "grīda": "floor"}
LAYER_KINDS = [("CLT", ("clt",)), ("latojums", ("latojum",)), ("siltinājums", ("siltinājum", "vate", "pir", "eps", "akmens")),
               ("membrāna", ("plēve", "membrān")), ("stiprinājums", ("skrūv", "stiprinā", "enkur", "naglas")),
               ("apdare", ("apdare", "dēlis", "ģipškarton", "fermacell", "flīz", "krāsa", "apmetum", "pārklājums", "segums")),
               ("plāksne", ("plāksne", "oSB", "osb", "saplāksnis", "dēļ"))]


@dataclass
class Candidate:
    id: str
    kind: str
    label: str
    data: dict
    page: int
    source: str                    # "vektors" | "teksts"
    confidence: str                # augsta | vidēja | zema
    evidence: str
    issues: list = field(default_factory=list)       # problēmas, kas jānovērš/jāpārbauda pirms apstiprināšanas
    status: str = "kandidāts"      # kandidāts | jāpārbauda (nepilni/nedroši dati — apstiprināšanai jānovērš)
    notes: list = field(default_factory=list)        # informatīvas piezīmes (neietekmē statusu)


@dataclass
class BuildingScan:
    candidates: list = field(default_factory=list)
    pages: list = field(default_factory=list)       # [{"page", "kind", "chars"}]
    notes: list = field(default_factory=list)
    vector: dict = field(default_factory=dict)

    def by_kind(self, kind):
        return [c for c in self.candidates if c.kind == kind]


def _n(text):
    return float(str(text).replace(",", "."))


def _to_mm(value, unit):
    return value * 1000.0 if unit.lower() == "m" else value


def _classify_layer(text):
    low = text.lower()
    for kind, words in LAYER_KINDS:
        if any(w.lower() in low for w in words):
            return kind, True
    return "cits", False


def parse_layers(text):
    """«fasādes dēlis 20 mm; latojums 50 mm c/c 600; CLT 100 mm» → [{name, kind, thickness_mm, step_mm, recognised}]"""
    layers = []
    for part in text.split(";"):
        part = " ".join(part.split()).strip(" .")
        if not part:
            continue
        thick = THICK_RE.search(part)
        step = STEP_RE.search(part)
        name = re.sub(r"\s+", " ", THICK_RE.sub("", STEP_RE.sub("", part))).strip(" ,.-")
        kind, known = _classify_layer(part)
        both = bool(re.search(r"abās\s+pusēs|abpusēj", part, re.I))
        layers.append({"name": name or part, "kind": kind, "thickness_mm": _n(thick.group(1)) if thick else None,
                       "step_mm": float(step.group(1)) if step else None, "recognised": known, "norm": 2.0 if both else None})
    return layers


def _loc_to_wall(rest, code):
    low = rest.lower()
    if "jumt" in low or code.upper().startswith("JL"):
        return "Jumts"
    if "iekšēj" in low or "iekšsien" in low:
        return "Iekšsiena"
    if "ārēj" in low or "ārsien" in low or "fasād" in low:
        return "Ārsiena"
    return None


def scan_ad_building(data: bytes) -> BuildingScan:
    """Skenē AD PDF un atgriež kandidātus ar lappusi/avotu/pārliecību/pierādījumu. Neko neraksta tāmē."""
    scan = BuildingScan()
    if not data.startswith(b"%PDF"):
        raise ValueError("Fails nav atpazīts kā PDF.")
    if len(data) > MAX_BYTES:
        raise ValueError("PDF pārsniedz 30 MB limitu.")
    counter = {"n": 0}

    def add(kind, label, d, page, source, conf, evidence, issues=None, notes=None):
        counter["n"] += 1
        issues = list(issues or [])
        cand = Candidate(f"C{counter['n']:03d}", kind, label, d, page, source, conf, evidence[:300], issues,
                         "jāpārbauda" if conf == LOW or issues else "kandidāts", list(notes or []))
        scan.candidates.append(cand)
        return cand

    page_texts, floor_pages = [], []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Ar paroli aizsargāts PDF netiek atbalstīts.")
        if len(doc) > MAX_PAGES:
            raise ValueError(f"PDF pārsniedz {MAX_PAGES} lapu limitu.")
        for index, page in enumerate(doc, 1):
            text = page.get_text("text", sort=True)
            kind, _reason = classify_page(text)
            page_texts.append(text)
            scan.pages.append({"page": index, "kind": kind, "chars": len(text)})
            if kind == "floor":
                floor_pages.append(index)

    seen_openings, tag_counts = {}, {}
    room_cands, facade_dims = [], []
    for page_no, text in enumerate(page_texts, 1):
        is_floor = page_no in floor_pages
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if not line:
                continue
            tag = TAG_RE.match(line)
            if tag and is_floor:
                tag_counts[tag.group("code")] = tag_counts.get(tag.group("code"), 0) + 1
                continue
            m = CEIL_RE.search(line)
            if m:
                mm_val = _to_mm(_n(m.group(1)), m.group(2))
                add(K_CEILING_H, f"Telpas augstums {mm_val:g} mm", {"height_mm": mm_val}, page_no, "teksts", HIGH, line)
                continue
            m = FACADE_TEXT_RE.search(line)
            if m:
                facade_dims.append((int(m.group("l")), int(m.group("w"))))
                add(K_FACADE, f"Fasādes kontūra {m.group('l')}×{m.group('w')} mm", {"length_mm": int(m.group("l")), "width_mm": int(m.group("w"))},
                    page_no, "teksts", MEDIUM, line, notes=["Ārējā fasādes kontūra nav grīdas pamatrāmis: tā netiek izmantota moduļa L/W; nobīdes netiek izsecinātas."])
                continue
            m = MODULE_TEXT_RE.search(line)
            if m:
                add(K_MODULE, f"Modulis {m.group('name')} {m.group('l')}×{m.group('w')} mm",
                    {"name": f"Modulis {m.group('name')}", "length_mm": int(m.group("l")), "width_mm": int(m.group("w"))}, page_no, "teksts", MEDIUM,
                    line, notes=["Izmēri nolasīti no teksta; vektoru ģeometrijas apstiprinājums var nebūt."])
                continue
            if TYPE_RE.match(line):
                _parse_type(line, page_no, add)
                continue
            if SLOPE_RE.match(line):
                _parse_slope(line, page_no, add)
                continue
            if GABLE_RE.match(line):
                _parse_gable(line, page_no, add)
                continue
            if WALL_RE.match(line):
                _parse_wall(line, page_no, add)
                continue
            m = OPENING_RE.match(line)
            if m:
                _parse_opening(m, line, page_no, add, seen_openings)
                continue
            m = ROOF_ANGLE_RE.search(line)
            if m:
                add(K_ROOF_ANGLE, f"Jumta slīpums {m.group(1)}°", {"angle_deg": _n(m.group(1))}, page_no, "teksts", MEDIUM, line,
                    notes=["Informatīvs: slīpnes ģeometrija jānorāda atsevišķi (garums, projekcija, leņķis)."])
                continue
            m = ROOM_RE.match(line)
            if m and not CEIL_RE.search(line):
                name, area = m.group("name").strip(" :-"), _n(m.group("area"))
                if FLOOR_TOTAL_RE.search(name):
                    add(K_FLOOR_NET, f"Neto grīdas platība {area:g} m²", {"area_m2": area}, page_no, "teksts", HIGH, line)
                elif TERRACE_RE.search(name):
                    add(K_TERRACE, f"Terase: {name} {area:g} m²", {"name": name, "area_m2": area}, page_no, "teksts", HIGH, line,
                        notes=["Terase netiek ieskaitīta iekštelpu platībā."])
                else:
                    room_cands.append(add(K_ROOM, f"{name} {area:g} m²", {"name": name, "area_m2": area}, page_no, "teksts", HIGH, line))
    # atveru skaita atbilstība plāna marķējumiem (Σ pa artikula kodu)
    totals = {}
    for entry in seen_openings.values():
        c = entry["cand"]
        totals.setdefault(c.data["name"], []).append(c)
    for code, cands in totals.items():
        tags = tag_counts.get(code)
        total = sum(c.data["count"] for c in cands)
        if tags is not None and tags != total:
            cands[0].issues.append(f"Specifikācijā kopā {total} gab., bet plānā atrasti {tags} marķējumi «{code}» — pārbaudi.")
            cands[0].status = "jāpārbauda"
    explicit_total = scan.by_kind(K_FLOOR_NET)
    if room_cands and not explicit_total:
        total = round(sum(c.data["area_m2"] for c in room_cands), 3)
        pages = sorted({c.page for c in room_cands})
        add(K_FLOOR_NET, f"Neto grīdas platība (telpu summa) {total:g} m²", {"area_m2": total, "derived": True}, pages[0], "teksts", MEDIUM,
            "Σ telpu laukumi: " + "; ".join(f"{c.data['name']} {c.data['area_m2']:g}" for c in room_cands),
            notes=["Aprēķināta kā atpazīto telpu laukumu summa; ja kāda telpa nav atpazīta, summa ir nepilna."])
    # vektoru moduļu kandidāti (esošā AD vektoru analīze)
    if floor_pages:
        scan.vector = analyze_pdf(data, floor_pages)
        for page in scan.vector.get("pages", []):
            for c in page.get("candidates", []):
                if not c.get("transferable") or not c.get("length_mm"):
                    scan.notes.append(f"Lapa {page['page']}: kontūra {c.get('id')} nav pārnesama ({c.get('status')}).")
                    continue
                conf = {CONSISTENT: HIGH, RECOGNISED: MEDIUM, UNCLEAR: LOW}.get(c["status"], LOW)
                issues = list(c.get("issues") or [])
                dims = (c["length_mm"], c["width_mm"])
                if any(dims == f or dims[::-1] == f for f in facade_dims):
                    issues.append("Izmēri sakrīt ar norādīto fasādes kontūru: nav pierādīts, ka tā ir grīdas pamatrāmja robeža.")
                    conf = LOW
                add(K_MODULE, f"Modulis (vektors) {c['length_mm']}×{c['width_mm']} mm",
                    {"name": f"Modulis {c['id']}", "length_mm": c["length_mm"], "width_mm": c["width_mm"], "status": c["status"],
                     "scale": (c.get("scale") or {}).get("denominator")}, page["page"], "vektors", conf,
                    f"Vektoru kontūra {c['id']}: {c['status']}; " + (c["evidence"][-1] if c.get("evidence") else ""), issues)
    if not scan.candidates:
        scan.notes.append("Nav atpazīts neviens lauks: PDF var būt attēls vai citāda notācija. Visi dati jāievada manuāli.")
    return scan


def _opt(pattern, line, cast=_n):
    m = re.search(pattern, line, re.I)
    return cast(m.group(1)) if m else None


def _parse_wall(line, page, add):
    length = _opt(r"\bL\s*=\s*(" + NUM + r")\s*m\b", line)
    hm = re.search(r"\bH\s*=\s*(" + NUM + r")\s*(mm|m)\b", line, re.I)
    low = line.lower()
    kind = "Ārsiena" if re.search(r"ārēj|ārsien|fasād", low) else ("Iekšsiena" if re.search(r"iekšēj|iekšsien|starpsien", low) else None)
    name = re.match(r"^\s*siena\s+([^:,]+)", line, re.I)
    wtype = re.search(r"tips\s+([A-ZĀČĒĢĪĶĻŅŠŪŽ]{1,3}\d+)", line)
    clt = _opt(r"CLT\s*(" + NUM + r")\s*mm", line)
    issues = []
    if length is None:
        issues.append("Garums (L=… m) nav nolasīts.")
    if not hm:
        issues.append("Augstums (H=…) nav nolasīts: tiks izmantots noklusējuma sienu augstums vai jāievada manuāli.")
    if kind is None:
        issues.append("Nav skaidrs, vai siena ir ārēja vai iekšēja: jānorāda manuāli.")
    height = _to_mm(_n(hm.group(1)), hm.group(2)) if hm else None
    conf = HIGH if (length is not None and height is not None and kind) else LOW
    nm = (name.group(1).strip() if name else "Siena")
    add(K_WALL, f"{nm}: {kind or '?'} L={length if length is not None else '?'} m", {
        "name": nm, "wall": kind, "length_m": length, "height_mm": height, "type": wtype.group(1) if wtype else "", "clt_mm": clt},
        page, "teksts", conf, line, issues)


def _parse_gable(line, page, add):
    base = _opt(r"pamats\s*=?\s*(" + NUM + r")\s*m\b", line)
    height = _opt(r"augstums\s*=?\s*(" + NUM + r")\s*m\b", line)
    name = re.match(r"^\s*zelmi[ņn]š\s+([^:,]+)", line, re.I)
    wtype = re.search(r"tips\s+([A-ZĀČĒĢĪĶĻŅŠŪŽ]{1,3}\d+)", line)
    clt = _opt(r"CLT\s*(" + NUM + r")\s*mm", line)
    issues = []
    if base is None or height is None:
        issues.append("Zelmiņa pamats/augstums nav pilnībā nolasīts.")
    nm = f"Zelmiņš {name.group(1).strip()}" if name else "Zelmiņš"
    add(K_GABLE, f"{nm}: ½ × {base if base is not None else '?'} × {height if height is not None else '?'} m",
        {"name": nm, "base_m": base, "height_m": height, "type": wtype.group(1) if wtype else "", "clt_mm": clt}, page, "teksts",
        HIGH if not issues else LOW, line, issues)


def _parse_slope(line, page, add):
    length = _opt(r"garums\s*=?\s*(" + NUM + r")\s*m\b", line)
    proj = _opt(r"projekcija\s*=?\s*(" + NUM + r")\s*m\b", line)
    ang = _opt(r"(?:leņķis|α)\s*=?\s*(" + NUM + r")\s*°", line)
    name = re.match(r"^\s*jumta\s+slīpne\s+([^:,]+)", line, re.I)
    wtype = re.search(r"tips\s+([A-ZĀČĒĢĪĶĻŅŠŪŽ]{1,3}\d+)", line)
    clt = _opt(r"CLT\s*(" + NUM + r")\s*mm", line)
    issues = []
    if None in (length, proj, ang):
        issues.append("Slīpnei jānolasa garums, horizontālā projekcija un leņķis; trūkstošais jāievada manuāli.")
    gross = round(length * proj / math.cos(math.radians(ang)), 4) if None not in (length, proj, ang) and 0 <= ang < 80 else None
    nm = f"Slīpne {name.group(1).strip()}" if name else "Slīpne"
    add(K_SLOPE, f"{nm}: bruto {gross if gross is not None else '?'} m²", {
        "name": nm, "length_m": length, "projection_m": proj, "angle_deg": ang, "gross_m2": gross, "type": wtype.group(1) if wtype else "",
        "clt_mm": clt}, page, "teksts", HIGH if not issues else LOW, line, issues)


def _parse_opening(m, line, page, add, seen):
    code, w, h, n = m.group("code"), int(m.group("w")), int(m.group("h")), int(m.group("n"))
    wall = _loc_to_wall(m.group("rest") or "", code)
    seg = re.search(r"posms\s+(.+?)\s*$", m.group("rest") or "", re.I)
    segment = seg.group(1).strip() if seg else ""
    key = (code, w, h, segment, wall)
    if key in seen:
        seen[key]["cand"].notes.append(f"Atvere «{code}»{(' posmā ' + segment) if segment else ''} atkārtojas lappusē {page}: dublikāts ignorēts "
                                       "(netiek atskaitīta divreiz).")                    # informatīvi: kandidāts pats nav apšaubāms
        return
    kind = "Durvis" if code.upper().startswith("D") else "Logs"
    issues = []
    if wall is None:
        issues.append("Atrašanās vieta (ārējais/iekšējais/jumta) nav norādīta: jāizvēlas manuāli; bez tās atvere netiek pārnesta.")
    cand = add(K_OPENING, f"{kind} {code} {w}×{h} ×{n} ({(wall or '?').lower()})", {
        "name": code, "kind": kind, "width_mm": w, "height_mm": h, "count": n, "wall": wall, "segment": segment},
        page, "teksts", HIGH if wall else LOW, line, issues)
    seen[key] = {"cand": cand}


def _parse_type(line, page, add):
    m = TYPE_RE.match(line)
    code, what, layers_text = m.group("code"), m.group("what").lower(), m.group("layers")
    applies = APPLIES[what]
    layers = parse_layers(layers_text)
    issues = []
    unknown = [l["name"] for l in layers if not l["recognised"]]
    if applies == "floor":
        issues.append("Grīdas tipi šajā versijā netiek pārnesti (grīda — rāmja kodols/CLT grīdas paneļi).")
    if unknown:
        issues.append("Slāņi ar neatpazītu veidu (jāpārbauda): " + ", ".join(unknown))
    if not layers:
        issues.append("Slāņi nav nolasīti.")
    add(K_TYPE, f"Tips {code} ({what}): {len(layers)} slāņi", {"code": code, "applies_to": applies, "layers": layers}, page, "teksts",
        HIGH if (layers and not unknown and applies != "floor") else MEDIUM if layers else LOW, line, issues)


# --- piemērošana projektam (TIKAI apstiprinātie kandidāti) -----------------------------------------------------------
@dataclass
class ApplyReport:
    applied: list = field(default_factory=list)           # (kandidāta ID, apraksts)
    skipped: list = field(default_factory=list)           # (kandidāta ID, iemesls)


def _prov(project, cand, field_name, note=""):
    ad = project.setdefault("ad_import", None) or {}
    ad.setdefault("stage", "AD")
    ad.setdefault("fields", [])
    ad["fields"].append({"candidate": cand.id, "field": field_name, "page": cand.page, "source": cand.source, "confidence": cand.confidence,
                         "evidence": cand.evidence[:160], "confirmed_by_user": True, "note": note})
    project["ad_import"] = ad


def apply_candidates(project: dict, scan: BuildingScan, accepted_ids, *, mode="add", ceiling_as_floor=True, use_type_recipes=True,
                     source_label="AD PDF") -> ApplyReport:
    """Ieraksta TIKAI lietotāja apstiprinātos kandidātus (`accepted_ids`) projektā. `mode`: «add» — dublikāti netiek pievienoti;
    «replace» — attiecīgās kategorijas saraksts tiek aizvietots. Esošie manuālie dati citās kategorijās netiek skarti."""
    report = ApplyReport()
    accepted = [c for c in scan.candidates if c.id in set(accepted_ids)]
    if mode == "replace":
        cleared = {K_MODULE: ("modules",), K_ROOM: (), K_TERRACE: ("terraces",), K_OPENING: ("openings",), K_GABLE: ("gables",),
                   K_SLOPE: ("roof_slopes",), K_TYPE: ("construction_types", "type_recipes")}
        kinds = {c.kind for c in accepted}
        for kind, keys in cleared.items():
            if kind in kinds:
                for key in keys:
                    project[key] = []
        if K_WALL in kinds:
            walls = {c.data.get("wall") for c in accepted if c.kind == K_WALL}
            if "Ārsiena" in walls:
                project["ext_walls"] = []
            if "Iekšsiena" in walls:
                project["int_walls"] = []
    label = source_label
    for c in accepted:
        d = c.data
        if c.status == "jāpārbauda" and c.confidence == LOW and c.kind in (K_WALL, K_GABLE, K_SLOPE, K_OPENING):
            pass                                           # nepilnus kandidātus pārbauda zemāk pēc konkrētiem laukiem
        src = f"{label} lpp. {c.page}, {c.source}, pārliecība {c.confidence}, apstiprināts"
        if c.kind == K_MODULE:
            existing = {(m.get("length_mm"), m.get("width_mm")) for m in project.get("modules", [])}
            if (d["length_mm"], d["width_mm"]) in existing:
                report.skipped.append((c.id, "modulis ar tādiem pašiem L/W jau ir"))
                continue
            mod = {"name": d["name"], "length_mm": d["length_mm"], "width_mm": d["width_mm"], "axes": "", "confirmed": True}
            project.setdefault("modules", []).append(mod)
            project.setdefault("module_fp", {})[str(len(project["modules"]) - 1)] = module_fp(mod)
            _prov(project, c, "modules")
            report.applied.append((c.id, c.label))
        elif c.kind == K_FLOOR_NET:
            project["floor_net_m2"] = d["area_m2"]
            note = "telpu summa" if d.get("derived") else "norādīts rasējumā"
            _prov(project, c, "floor_net_m2", note)
            if ceiling_as_floor and project.get("ceiling_m2") in (None, 0):
                project["ceiling_m2"] = d["area_m2"]
                _prov(project, c, "ceiling_m2", "PIEŅĒMUMS: griestu platība = neto grīdas platība (plakani griesti)")
            report.applied.append((c.id, c.label))
        elif c.kind == K_TERRACE:
            terr = project.setdefault("terraces", [])
            if any(t.get("name") == d["name"] and t.get("area_m2") == d["area_m2"] for t in terr):
                report.skipped.append((c.id, "terase jau ir"))
                continue
            terr.append({"name": d["name"], "area_m2": d["area_m2"], "article": None})
            _prov(project, c, "terraces")
            report.applied.append((c.id, c.label))
        elif c.kind == K_CEILING_H:
            project["wall_height_mm"] = d["height_mm"]
            _prov(project, c, "wall_height_mm")
            report.applied.append((c.id, c.label))
        elif c.kind == K_WALL:
            if d["wall"] is None or d["length_m"] is None:
                report.skipped.append((c.id, "trūkst veida (ārēja/iekšēja) vai garuma: ievadi manuāli"))
                continue
            key = "ext_walls" if d["wall"] == "Ārsiena" else "int_walls"
            lst = project.setdefault(key, [])
            if any(w.get("name") == d["name"] and w.get("length_m") == d["length_m"] for w in lst):
                report.skipped.append((c.id, "sienas posms jau ir"))
                continue
            lst.append({"name": d["name"], "length_m": d["length_m"], "height_mm": d["height_mm"], "type": d["type"], "clt_mm": d["clt_mm"]})
            _prov(project, c, key)
            report.applied.append((c.id, c.label))
        elif c.kind == K_GABLE:
            if d["base_m"] is None or d["height_m"] is None:
                report.skipped.append((c.id, "zelmiņa izmēri nav pilni: ievadi manuāli"))
                continue
            gl = project.setdefault("gables", [])
            if any(g.get("name") == d["name"] for g in gl):
                report.skipped.append((c.id, "zelmiņš jau ir"))
                continue
            gl.append({"name": d["name"], "base_m": d["base_m"], "height_m": d["height_m"], "type": d["type"], "clt_mm": d["clt_mm"]})
            _prov(project, c, "gables")
            report.applied.append((c.id, c.label))
        elif c.kind == K_OPENING:
            if d["wall"] is None:
                report.skipped.append((c.id, "atrašanās vieta nav norādīta: izvēlies manuāli"))
                continue
            ops = project.setdefault("openings", [])
            if any(o.get("name") == d["name"] and o.get("width_mm") == d["width_mm"] and o.get("height_mm") == d["height_mm"]
                   and o.get("wall") == d["wall"] and (o.get("segment") or "") == d["segment"] for o in ops):
                report.skipped.append((c.id, "atvere jau ir (netiek atskaitīta divreiz)"))
                continue
            ops.append({"kind": d["kind"], "name": d["name"], "article": None, "width_mm": d["width_mm"], "height_mm": d["height_mm"],
                        "count": d["count"], "wall": d["wall"], "segment": d["segment"]})
            _prov(project, c, "openings")
            report.applied.append((c.id, c.label))
        elif c.kind == K_SLOPE:
            if None in (d["length_m"], d["projection_m"], d["angle_deg"]):
                report.skipped.append((c.id, "slīpnes dati nav pilni: ievadi manuāli"))
                continue
            sl = project.setdefault("roof_slopes", [])
            if any(x.get("name") == d["name"] for x in sl):
                report.skipped.append((c.id, "slīpne jau ir"))
                continue
            sl.append({"name": d["name"], "length_m": d["length_m"], "projection_m": d["projection_m"], "angle_deg": d["angle_deg"],
                       "area_m2": None, "clt_mm": d["clt_mm"], "type": d["type"], "confirmed": True})
            project.setdefault("roof", {})["mode"] = "slopes"
            _prov(project, c, "roof_slopes")
            report.applied.append((c.id, c.label))
        elif c.kind == K_TYPE:
            if d["applies_to"] == "floor":
                report.skipped.append((c.id, "grīdas tipi netiek pārnesti"))
                continue
            types = project.setdefault("construction_types", [])
            if any(t.get("code") == d["code"] for t in types):
                report.skipped.append((c.id, f"tips {d['code']} jau ir"))
                continue
            types.append({"code": d["code"], "name": c.label, "applies_to": d["applies_to"], "source": src})
            trs = project.setdefault("type_recipes", [])
            for layer in d["layers"]:
                unit = {"CLT": "m³", "siltinājums": "m³", "latojums": "m", "stiprinājums": "gab."}.get(layer["kind"], "m²")
                trs.append({"type": d["code"], "name": layer["name"], "kind": layer["kind"], "unit": unit,
                            "thickness_mm": layer["thickness_mm"], "step_mm": layer["step_mm"], "norm": layer.get("norm"), "article": None, "spec": "",
                            "waste_pct": None, "pack_size": None, "approved": False, "enabled": True, "detail": "detalizēts",
                            "assumption": "", "module": "", "stage": "", "source": src})
            if use_type_recipes:
                project["layers_mode"] = "types"
            _prov(project, c, "construction_types", f"{len(d['layers'])} slāņi (normas/cenas jāievada)")
            report.applied.append((c.id, c.label))
        else:
            report.skipped.append((c.id, "kategorija netiek pārnesta (informatīva)"))
    ensure_ids(project)
    return report
