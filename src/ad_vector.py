"""AD PDF vektoru ģeometrijas analīze: moduļa kontūras kandidāti ar pierādījumiem (Issue #6, PROTOTIPS).

Atsevišķs modulis. NEMAINA `src/frame_vectors.py` (tas ir PD siju kandidātu detektors pēc krāsas)
un nesajaucams ar to. Analīze netiek balstīta uz lielāko skaitli, krāsu vai biežumu.

Ko dara:
1. No lapas vektoriem iegūst slēgtas ortogonālas kontūras (`re`, `qu`, slēgtas `l` ķēdes) un
   atsevišķus horizontālus/vertikālus nogriežņus; no teksta: skaitļus, mērogu, marķējumus.
2. Atrod izmēru norādes: skaitlis + tuvākā nepārtrauktā izmēru līnija + izvilkuma līnijas galos.
3. Izmēru norādi saista ar kontūru TIKAI ja izmēru/izvilkuma līniju gali sakrīt ar kontūras malām.
4. Mērogu pārbauda pret izmēriem: izsecinātais mērogs = izmēra teksts / (izmērītais garums pt).
   Virsraksta mērogs netiek vienkārši pieņemts.
5. Kandidātam piešķir statusu un pierādījumus (lapa, bbox, mērogs un avots, izmēru norādes, problēmas).

Statusi: "ģeometriski saskaņots" (taisnstūris + abi izmēri telpiski saistīti ar kontūru + mērogs pārbaudīts
+ moduļa teksta marķējums, bez pretrunām), "atpazīts" (tas pats bez moduļa marķējuma), "neskaidrs"
(pierādījumu nepietiek) un "atteikums" (neregulāra forma vai pretrunas: L/W netiek dots).
**Neviens statuss nepierāda, ka kontūra ir grīdas rāmja (nevis fasādes) konstrukcijas robeža**; teksts
"MODULIS" kontūras iekšpusē ir tikai marķējums. Lietotāja apstiprinājums vienmēr ir obligāts.
Pielaides (±2 pt, ±2 %, 8 pt) ir PROTOTIPA pielaides līdz reālu rasējumu validācijai.
Telpas un terases netiek uzskatītas par moduļiem. Blakus kontūras netiek apvienotas, un L/U forma
netiek sadalīta. Lietotājs vienmēr apstiprina izmērus (src/ad_ui.py).

Zināmie ierobežojumi: tikai ortogonālas kontūras; kontūra, kas zīmēta no atsevišķiem nogriežņiem, netiek
atpazīta; izmēru ķēdes netiek apvienotas; teksts, kas nav ciparu virkne (3–5 cipari), netiek lasīts kā
izmērs; sintētiski rezultāti NEPIERĀDA, ka tiks atpazīti reāli AD rasējumi.
"""
import math
import re

import pymupdf

from src.ad_plan import TERRACE_RE

MM_PER_PT = 25.4 / 72
# PROTOTIPA pielaides: nav validētas uz reāliem rasējumiem (jāpārskata pēc validācijas).
AXIS_TOL = 0.3          # pt: nogrieznis uzskatāms par horizontālu/vertikālu
EDGE_TOL = 2.0          # pt: izmēru līnijas gali pret kontūras malu
EXT_TOL = 1.5           # pt: izvilkuma līnijas novietojums pret izmēru līnijas galu
EXT_LINK_TOL = 8.0      # pt: izvilkuma līnijas tuvākajam galam jāatrodas pie kontūras malas
ASSOC_DIST = 14.0       # pt: izmēra teksta centrs pret izmēru līniju
SCALE_TOL = 0.02        # relatīvā pielaide mērogam un izmēru atbilstībai
FRAME_AREA_RATIO = 0.80
STANDARD_SCALES = (10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500)

CONSISTENT, RECOGNISED, UNCLEAR, REFUSED = "ģeometriski saskaņots", "atpazīts", "neskaidrs", "atteikums"
TRANSFERABLE = (CONSISTENT, RECOGNISED, UNCLEAR)
DISCLAIMER = ("Statuss apliecina tikai ģeometrisku saskaņotību (kontūra, izmēru norādes, mērogs). Tas NEPIERĀDA, "
              "ka kontūra ir grīdas rāmja (nevis fasādes) konstrukcijas robeža; lietotāja apstiprinājums ir "
              "obligāts. Pielaides (±2 pt, ±2 %, 8 pt) ir prototipa pielaides, nevalidētas uz reāliem rasējumiem.")

NUMBER_RE = re.compile(r"\d{3,5}")
SCALE_RE = re.compile(r"(?<![\d:])1\s*:\s*(\d{1,4})(?!\d)")
MODULE_RE = re.compile(r"\bmodul\w*|\bmodule\b", re.I)
BOUNDARY_RE = re.compile(r"robež|boundary|joint|savienojum", re.I)
ROOM_RE = re.compile(
    r"\b(?:virtuv\w*|kitchen|istab\w*|room|telp\w*|guļamistab\w*|bedroom|vann\w*|bathroom|wc|"
    r"dzīvojam\w*|living|hall|gaiten\w*|noliktav\w*|storage)\b|\d+(?:[.,]\d+)?\s*m\s*[2²]", re.I)


def _r(value, digits=1):
    return round(float(value), digits)


def _bbox(values):
    return [_r(v, 2) for v in values]


# --- ģeometrijas iegūšana ------------------------------------------------------------------------
def _close(a, b, tol=0.5):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _simplify(points):
    """Noņem virsotnes, kas atrodas uz vienas taisnes (kolineāras)."""
    changed = True
    while changed and len(points) > 3:
        changed = False
        for i in range(len(points)):
            a, b, c = points[i - 1], points[i], points[(i + 1) % len(points)]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cross) < 1e-6:
                del points[i]
                changed = True
                break
    return points


def _orthogonal(points):
    return all(abs(points[i][0] - points[(i + 1) % len(points)][0]) <= AXIS_TOL
               or abs(points[i][1] - points[(i + 1) % len(points)][1]) <= AXIS_TOL
               for i in range(len(points)))


def _contour(points, width, dashed):
    points = [(float(x), float(y)) for x, y in points]
    points = _simplify(points)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    orthogonal = _orthogonal(points)
    is_rect = orthogonal and len(points) == 4
    return {"kind": "rectangle" if is_rect else "polygon", "vertices": points, "bbox": bbox,
            "orthogonal": orthogonal, "line_width": width, "dashed": dashed}


def _closed_chain(items):
    """Slēgtas 'l' ķēdes virsotnes vai None."""
    if len(items) < 3 or any(item[0] != "l" for item in items):
        return None
    for current, following in zip(items, items[1:]):
        if not _close(current[2], following[1]):
            return None
    return [(items[0][1].x, items[0][1].y)] + [(item[2].x, item[2].y) for item in items[:-1]] \
        if _close(items[-1][2], items[0][1]) else None


def _extract_geometry(page):
    contours, segments, ignored = [], [], {"curves": 0, "diagonal_segments": 0, "unstroked": 0}
    seen = set()
    for drawing in page.get_drawings():
        if drawing.get("color") is None:           # tikai aizpildījums, nav līnijas
            ignored["unstroked"] += 1
            continue
        dashes = (drawing.get("dashes") or "").replace(" ", "")
        dashed = bool(dashes) and not dashes.startswith("[]")
        width = float(drawing.get("width") or 0.0)
        items = drawing["items"]
        chain = _closed_chain(items)
        if chain is None and drawing.get("closePath") and all(i[0] == "l" for i in items) and len(items) >= 2:
            chain = [(items[0][1].x, items[0][1].y)] + [(i[2].x, i[2].y) for i in items]
        if chain is not None:
            candidates = [_contour(chain, width, dashed)]
        else:
            candidates = []
            for item in items:
                kind = item[0]
                if kind == "re":
                    r = item[1]
                    candidates.append(_contour([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)],
                                               width, dashed))
                elif kind == "qu":
                    q = item[1]
                    candidates.append(_contour([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y),
                                                (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)], width, dashed))
                elif kind == "l":
                    p1, p2 = item[1], item[2]
                    dx, dy = abs(p2.x - p1.x), abs(p2.y - p1.y)
                    if dy <= AXIS_TOL and dx > AXIS_TOL:
                        segments.append({"orientation": "H", "pos": (p1.y + p2.y) / 2,
                                         "a": min(p1.x, p2.x), "b": max(p1.x, p2.x),
                                         "dashed": dashed, "width": width})
                    elif dx <= AXIS_TOL and dy > AXIS_TOL:
                        segments.append({"orientation": "V", "pos": (p1.x + p2.x) / 2,
                                         "a": min(p1.y, p2.y), "b": max(p1.y, p2.y),
                                         "dashed": dashed, "width": width})
                    else:
                        ignored["diagonal_segments"] += 1
                elif kind == "c":
                    ignored["curves"] += 1
        for contour in candidates:
            key = tuple(round(v, 1) for v in contour["bbox"]) + (len(contour["vertices"]),)
            if key not in seen:
                seen.add(key)
                contours.append(contour)
    return contours, segments, ignored


def _extract_texts(page):
    texts = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            dx, dy = line["dir"]
            orientation = "H" if abs(dy) < 0.2 else ("V" if abs(dx) < 0.2 else "D")
            texts.append({"text": text, "bbox": (x0, y0, x1, y1), "center": ((x0 + x1) / 2, (y0 + y1) / 2),
                          "orientation": orientation})
    return texts


# --- izmēru norādes un mērogs ------------------------------------------------------------------
def _find_dimensions(texts, segments):
    solid = [s for s in segments if not s["dashed"]]
    dimensions = []
    for text in texts:
        if not NUMBER_RE.fullmatch(text["text"]) or text["orientation"] not in ("H", "V"):
            continue
        orient = text["orientation"]
        cx, cy = text["center"]
        best = None
        for seg in solid:
            if seg["orientation"] != orient:
                continue
            across, along = (abs(cy - seg["pos"]), cx) if orient == "H" else (abs(cx - seg["pos"]), cy)
            if across <= ASSOC_DIST and seg["a"] <= along <= seg["b"]:
                if best is None or across < best[0]:
                    best = (across, seg)
        if best is None:
            continue
        seg = best[1]
        cross = "V" if orient == "H" else "H"
        ext = []
        for end in (seg["a"], seg["b"]):
            ext.append([(o["a"], o["b"]) for o in solid
                        if o["orientation"] == cross and abs(o["pos"] - end) <= EXT_TOL
                        and o["a"] - 4 <= seg["pos"] <= o["b"] + 4])
        dimensions.append({
            "id": f"D{len(dimensions) + 1}", "orientation": orient, "value_mm": int(text["text"]),
            "text_bbox": text["bbox"], "start": seg["a"], "end": seg["b"], "position": seg["pos"],
            "measured_pt": seg["b"] - seg["a"], "extension_start": bool(ext[0]), "extension_end": bool(ext[1]),
            "ext_start_segs": ext[0], "ext_end_segs": ext[1],
        })
    return dimensions


def _link_to_contour(dim, bbox):
    """Telpiska sasaiste starp izmēru norādi un konkrētu kontūru.

    ("linked", mala, sprauga): abu izvilkuma līniju tuvākie gali atrodas pie vienas šīs kontūras malas.
    ("weak", None, None): izvilkuma līniju nav abos galos; sakrīt tikai koordinātas (nav pierādīts, ka
    norāde pieder šai kontūrai: citā vietā lapā var būt cita kontūra ar tādu pašu platumu).
    ("foreign", None, None): izvilkuma līnijas ir, bet sākas citur: norāde pieder citai kontūrai.
    """
    if not (dim["ext_start_segs"] and dim["ext_end_segs"]):
        return "weak", None, None
    x0, y0, x1, y1 = bbox
    edges = ((("augšējās", y0), ("apakšējās", y1)) if dim["orientation"] == "H"
             else (("kreisās", x0), ("labās", x1)))
    best = None
    for side, edge in edges:
        gap = max(min(min(abs(a - edge), abs(b - edge)) for a, b in segs)
                  for segs in (dim["ext_start_segs"], dim["ext_end_segs"]))
        if gap <= EXT_LINK_TOL and (best is None or gap < best[1]):
            best = (side, gap)
    return ("linked", best[0], best[1]) if best else ("foreign", None, None)


def _declared_scale(texts):
    found = []
    for text in texts:
        for match in SCALE_RE.finditer(text["text"]):
            denominator = int(match.group(1))
            if 2 <= denominator <= 2000:
                found.append({"denominator": denominator, "text": match.group(0).replace(" ", ""),
                              "bbox": _bbox(text["bbox"])})
    distinct = sorted({f["denominator"] for f in found})
    if not found:
        return {"status": "nav", "denominator": None, "sources": []}
    if len(distinct) == 1:
        return {"status": "viens", "denominator": distinct[0], "sources": found}
    return {"status": "vairāki", "denominator": None, "sources": found}


def _implied(value_mm, extent_pt):
    return value_mm / (extent_pt * MM_PER_PT) if extent_pt > 0 else float("inf")


def _nearest_standard(denominator):
    best = min(STANDARD_SCALES, key=lambda s: abs(s - denominator))
    return best if abs(best - denominator) / best <= SCALE_TOL else None


def _evaluate_scale(declared, implied_values):
    """Mēroga statuss pret izmēru norādēm: pārbaudīts | nav norādīts | pretrunā | nenosakāms."""
    if not implied_values:
        return {"status": "nenosakāms", "implied": [], "denominator": None, "source": None,
                "notes": ["Nav izmēru norāžu, ar ko mērogu pārbaudīt."]}
    low, high = min(implied_values), max(implied_values)
    consistent = (high - low) / low <= SCALE_TOL
    mean = sum(implied_values) / len(implied_values)
    implied = [_r(v, 2) for v in implied_values]
    if declared["status"] == "viens":
        n = declared["denominator"]
        agrees = all(abs(v - n) / n <= SCALE_TOL for v in implied_values)
        source = f"virsraksta teksta '{declared['sources'][0]['text']}'"
        if agrees:
            return {"status": "pārbaudīts", "implied": implied, "denominator": n, "source": source,
                    "notes": []}
        return {"status": "pretrunā", "implied": implied, "denominator": n, "source": source,
                "notes": [f"Norādīts mērogs 1:{n}, bet izmēru norādes izsaka 1:" +
                          ", 1:".join(f"{v:.1f}" for v in implied) + "."]}
    if declared["status"] == "vairāki":
        return {"status": "nenosakāms", "implied": implied, "denominator": None, "source": None,
                "notes": ["Lapā norādīti vairāki dažādi mērogi: virsraksta mērogs netiek pieņemts."]}
    if len(implied_values) >= 2 and consistent:
        standard = _nearest_standard(mean)
        return {"status": "nav norādīts", "implied": implied, "denominator": standard or _r(mean, 1),
                "source": "izsecināts no izmēru norādēm",
                "notes": ["Mērogs lapā nav norādīts; izsecināts no izmēru norādēm (jāpārbauda)."]}
    return {"status": "nenosakāms", "implied": implied, "denominator": None, "source": None,
            "notes": ["Mērogs nav norādīts un izmēru norādes nav savstarpēji saskaņotas."]}


# --- kontūru lomas, kaimiņattiecības ----------------------------------------------------------
def _area(bbox):
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _contains_point(bbox, point, margin=1.0):
    return bbox[0] + margin < point[0] < bbox[2] - margin and bbox[1] + margin < point[1] < bbox[3] - margin


def _contains_bbox(outer, inner, tol=1.0):
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1]
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol and outer != inner)


def _shared_edge(a, b):
    """('H'|'V', pos, lo, hi) ja a un b taisnstūri saskaras pa malu."""
    tol = EDGE_TOL
    for first, second in ((a, b), (b, a)):
        if abs(first[3] - second[1]) <= tol:
            lo, hi = max(first[0], second[0]), min(first[2], second[2])
            if hi - lo > 0.5 * min(first[2] - first[0], second[2] - second[0]):
                return ("H", (first[3] + second[1]) / 2, lo, hi)
        if abs(first[2] - second[0]) <= tol:
            lo, hi = max(first[1], second[1]), min(first[3], second[3])
            if hi - lo > 0.5 * min(first[3] - first[1], second[3] - second[1]):
                return ("V", (first[2] + second[0]) / 2, lo, hi)
    return None


def _separator_evidence(edge, segments, texts):
    orient, pos, lo, hi = edge
    for seg in segments:
        if seg["orientation"] == orient and abs(seg["pos"] - pos) <= EDGE_TOL:
            covered = min(seg["b"], hi) - max(seg["a"], lo)
            if covered >= 0.8 * (hi - lo):
                kind = "raustīta" if seg["dashed"] else "nepārtraukta"
                return {"type": f"{kind} līnija gar kopējo malu", "position_pt": _r(pos, 2),
                        "span_pt": [_r(max(seg["a"], lo), 2), _r(min(seg["b"], hi), 2)],
                        "dashed": seg["dashed"]}
    for text in texts:
        if BOUNDARY_RE.search(text["text"]):
            cx, cy = text["center"]
            along, across = (cx, cy) if orient == "H" else (cy, cx)
            if lo <= along <= hi and abs(across - pos) <= 12:
                return {"type": f"teksts '{text['text']}' pie kopējās malas", "position_pt": _r(pos, 2),
                        "span_pt": [_r(lo, 2), _r(hi, 2)], "dashed": False}
    return None


# --- lapas analīze -----------------------------------------------------------------------------
def analyze_page(page, page_number):
    """Vienas lapas vektoru analīze. Atgriež JSON-saderīgu dict (glabājams sesijā)."""
    media = page.mediabox
    page_area = media.width * media.height
    contours, segments, ignored = _extract_geometry(page)
    texts = _extract_texts(page)
    base = {"page": page_number, "mediabox_pt": [_r(media.width, 2), _r(media.height, 2)],
            "rotation": page.rotation, "ignored": ignored, "candidates": [], "excluded": [],
            "dimensions": [], "notes": []}
    if not contours and not segments:
        return {**base, "status": "no_vector_geometry", "scale": None,
                "notes": ["Lapā nav vektoru ģeometrijas (iespējams, attēls vai skenējums): "
                          "automātiska kontūru atpazīšana nav iespējama. Ievadi izmērus manuāli."]}

    dimensions = _find_dimensions(texts, segments)
    declared = _declared_scale(texts)
    excluded = []

    # lapas rāmis netiek skatīts kā kontūra
    live = []
    for contour in contours:
        if _area(contour["bbox"]) >= FRAME_AREA_RATIO * page_area:
            excluded.append({"kind": "page_frame", "bbox": _bbox(contour["bbox"]), "label": None,
                             "reason": "Lapas rāmis."})
        else:
            live.append(contour)

    # teksta marķējums pieder mazākajai kontūrai, kuras iekšpusē atrodas teksta centrs
    label_texts = [t for t in texts if not NUMBER_RE.fullmatch(t["text"])]
    for contour in live:
        contour["labels"] = []
    for text in label_texts:
        containing = [c for c in live if _contains_point(c["bbox"], text["center"])]
        if containing:
            min(containing, key=lambda c: _area(c["bbox"]))["labels"].append(text["text"])

    measured = []
    for contour in live:
        x0, y0, x1, y1 = contour["bbox"]
        matches = []
        for dim in dimensions:
            lo, hi = (x0, x1) if dim["orientation"] == "H" else (y0, y1)
            if abs(dim["start"] - lo) <= EDGE_TOL and abs(dim["end"] - hi) <= EDGE_TOL:
                link, side, gap = _link_to_contour(dim, contour["bbox"])
                if link != "foreign":          # izvilkuma līnijas sākas citur: norāde pieder citai kontūrai
                    matches.append({**dim, "link": link, "link_side": side, "link_gap": gap})
        contour["matches"] = matches
        labels = contour["labels"]
        contour["module_label"] = next((l for l in labels if MODULE_RE.search(l)), None)
        terrace = next((l for l in labels if TERRACE_RE.search(l)), None)
        room = next((l for l in labels if ROOM_RE.search(l)), None)
        if not matches:
            excluded.append({"kind": "unmeasured", "bbox": _bbox(contour["bbox"]),
                             "label": ", ".join(labels) or None,
                             "reason": "Kontūrai nav piesaistītas izmēru norādes (nav kandidāts)."})
        elif terrace and not contour["module_label"]:
            excluded.append({"kind": "terrace", "bbox": _bbox(contour["bbox"]), "label": terrace,
                             "dimensions": [d["value_mm"] for d in matches],
                             "reason": f"Terase (marķējums '{terrace}'): netiek uzskatīta par moduli."})
        elif room and not contour["module_label"]:
            excluded.append({"kind": "room", "bbox": _bbox(contour["bbox"]), "label": room,
                             "dimensions": [d["value_mm"] for d in matches],
                             "reason": f"Telpas kontūra (marķējums '{room}'): netiek uzskatīta par moduli."})
        else:
            contour["role_conflict"] = bool(contour["module_label"] and (terrace or room))
            measured.append(contour)

    # ligzdotas kontūras: ja tikai vienai ir moduļa marķējums, otra tiek izslēgta; citādi neskaidrība
    nested_ambiguous = set()
    dropped = set()
    for i, a in enumerate(measured):
        for j, b in enumerate(measured):
            if i != j and _contains_bbox(b["bbox"], a["bbox"]):        # a ir b iekšpusē
                if bool(a["module_label"]) != bool(b["module_label"]):
                    other = j if a["module_label"] else i
                    dropped.add(other)
                else:
                    nested_ambiguous.update((i, j))
    final = []
    for index, contour in enumerate(measured):
        if index in dropped:
            excluded.append({"kind": "nested", "bbox": _bbox(contour["bbox"]), "label": None,
                             "dimensions": [d["value_mm"] for d in contour["matches"]],
                             "reason": "Ligzdota kontūra: moduļa marķējums ir citai kontūrai."})
        else:
            contour["nested_ambiguous"] = index in nested_ambiguous
            final.append(contour)
    final.sort(key=lambda c: (round(c["bbox"][1]), c["bbox"][0]))

    candidates = [_build_candidate(page_number, n, c, declared) for n, c in enumerate(final, 1)]

    # blakus esošas kontūras: apvienot vai sadalīt nedrīkst bez pierādītas robežas
    for i, a in enumerate(final):
        for j in range(i + 1, len(final)):
            b = final[j]
            if a["kind"] != "rectangle" or b["kind"] != "rectangle":
                continue
            edge = _shared_edge(a["bbox"], b["bbox"])
            if not edge:
                continue
            separator = _separator_evidence(edge, segments, texts)
            for k, other in ((i, j), (j, i)):
                cand = candidates[k]
                cand["boundary"]["adjacent_to"].append(candidates[other]["id"])
                cand["boundary"]["neighbours"].append({"id": candidates[other]["id"], "separator": separator})
                if separator:
                    cand["boundary"]["separator"] = cand["boundary"]["separator"] or separator
                    cand["evidence"].append(
                        f"Moduļu robeža ar {candidates[other]['id']} marķēta zīmējumā: {separator['type']} "
                        f"(pozīcija {separator['position_pt']} pt).")
                else:
                    cand["issues"].append(
                        f"Blakus kontūra {candidates[other]['id']}: moduļu robeža zīmējumā nav marķēta "
                        "(var būt viens modulis vai divi); kontūras netiek apvienotas.")
    for cand in candidates:
        _finalize_status(cand)

    ordered = sorted(excluded, key=lambda e: (e["bbox"][1], e["bbox"][0]))
    scale = {"declared": declared, "dimension_implied": [
        {"dimension": d["id"], "value_mm": d["value_mm"], "measured_pt": _r(d["measured_pt"], 2),
         "denominator": _r(_implied(d["value_mm"], d["measured_pt"]), 2)} for d in dimensions]}
    return {**base, "status": "ok", "scale": scale, "candidates": candidates, "excluded": ordered,
            "dimensions": [{"id": d["id"], "orientation": d["orientation"], "value_mm": d["value_mm"],
                            "text_bbox": _bbox(d["text_bbox"]), "measured_pt": _r(d["measured_pt"], 2),
                            "start_pt": _r(d["start"], 2), "end_pt": _r(d["end"], 2),
                            "position_pt": _r(d["position"], 2),
                            "extension_lines": [d["extension_start"], d["extension_end"]]}
                           for d in dimensions]}


def _build_candidate(page_number, number, contour, declared):
    x0, y0, x1, y1 = contour["bbox"]
    cid = f"P{page_number}-K{number}"
    candidate = {
        "id": cid, "page": page_number, "shape": contour["kind"], "bbox_pt": _bbox(contour["bbox"]),
        "vertices_pt": [[_r(x, 2), _r(y, 2)] for x, y in contour["vertices"]],
        "line_width_pt": _r(contour["line_width"], 2), "length_mm": None, "width_mm": None,
        "status": UNCLEAR, "evidence": [], "issues": [], "transferable": False,
        "boundary": {"label": contour["module_label"], "adjacent_to": [], "separator": None,
                     "neighbours": []},
        "scale": None, "dimensions": [], "observed_mm": {"horizontal": None, "vertical": None},
        "disclaimer": DISCLAIMER,
        "_flags": {"nested_ambiguous": contour["nested_ambiguous"],
                   "role_conflict": contour.get("role_conflict", False)},
    }
    extents = {"H": x1 - x0, "V": y1 - y0}
    chosen, conflicts = {}, []
    pool = [d for d in contour["matches"]]
    for orient in ("H", "V"):           # telpiski saistītās norādes ir prioritāras pār vājajām
        if any(d["link"] == "linked" for d in pool if d["orientation"] == orient):
            pool = [d for d in pool if d["orientation"] != orient or d["link"] == "linked"]
    for dim in pool:
        previous = chosen.get(dim["orientation"])
        if previous is None:
            chosen[dim["orientation"]] = dim
        elif previous["value_mm"] != dim["value_mm"]:
            conflicts.append(dim["orientation"])
    for orient in set(conflicts):
        chosen.pop(orient, None)
        candidate["issues"].append("Vienai malai ir vairākas pretrunīgas izmēru norādes: izmērs netiek noteikts.")
    candidate["observed_mm"] = {"horizontal": chosen["H"]["value_mm"] if "H" in chosen else None,
                                "vertical": chosen["V"]["value_mm"] if "V" in chosen else None}
    candidate["_chosen"] = chosen
    implied_values = []
    for orient, dim in chosen.items():
        implied = _implied(dim["value_mm"], extents[orient])
        implied_values.append(implied)
        name = "Horizontālā" if orient == "H" else "Vertikālā"
        ext = dim["extension_start"] and dim["extension_end"]
        linked = dim["link"] == "linked"
        candidate["dimensions"].append({
            "id": dim["id"], "orientation": orient, "value_mm": dim["value_mm"],
            "text_bbox_pt": _bbox(dim["text_bbox"]), "measured_pt": _r(extents[orient], 2),
            "implied_denominator": _r(implied, 2), "extension_lines_both_ends": ext,
            "linked_to_contour": linked, "link_side": dim["link_side"],
            "link_gap_pt": _r(dim["link_gap"], 2) if dim["link_gap"] is not None else None})
        candidate["evidence"].append(
            f"{name} izmēru norāde '{dim['value_mm']}' ({dim['id']}): izmēru līnijas gali "
            f"({_r(dim['start'], 1)}; {_r(dim['end'], 1)} pt) sakrīt ar kontūras malām (prototipa pielaide "
            f"±{EDGE_TOL} pt); izmērītais garums {_r(extents[orient], 1)} pt, izsecinātais mērogs 1:{implied:.1f}"
            + (f"; izvilkuma līnijas sākas pie šīs kontūras {dim['link_side']} malas (sprauga "
               f"{_r(dim['link_gap'], 1)} pt ≤ {EXT_LINK_TOL} pt, prototipa pielaide)." if linked
               else "; izvilkuma līniju nav abos galos: saistība ar šo kontūru NAV pierādīta telpiski."))
        if not linked:
            candidate["issues"].append(
                f"{name} izmēru norāde ({dim['id']}) tikai sakrīt pēc koordinātēm ar kontūras malām; "
                "izvilkuma līnijas nav pierādītas pie šīs kontūras, tāpēc saistība nav droša "
                "(var piederēt citai kontūrai ar tādu pašu izmēru).")
    scale = _evaluate_scale(declared, implied_values)
    candidate["scale"] = scale
    candidate["issues"].extend(scale["notes"])
    if scale["status"] == "pārbaudīts":
        candidate["evidence"].append(
            f"Mērogs 1:{scale['denominator']} no {scale['source']} pārbaudīts pret izmēru norādēm "
            f"(izsecinātie: {', '.join(f'1:{v}' for v in scale['implied'])}).")
    elif scale["status"] == "nav norādīts":
        candidate["evidence"].append(
            f"Mērogs nav norādīts; no izmēru norādēm izsecināts 1:{scale['denominator']}.")
    candidate["evidence"].insert(0, (
        f"{'Taisnstūra' if contour['kind'] == 'rectangle' else 'Neregulāra ortogonāla'} kontūra lapā "
        f"{page_number}: bbox ({_r(x0, 1)}; {_r(y0, 1)})–({_r(x1, 1)}; {_r(y1, 1)}) pt, "
        f"{len(contour['vertices'])} virsotnes, līnijas biezums {_r(contour['line_width'], 1)} pt."))
    if contour["module_label"]:
        candidate["evidence"].append(
            f"Moduļa teksta marķējums '{contour['module_label']}' kontūras iekšpusē (marķējums, nevis "
            "konstrukcijas robežas pierādījums).")
    return candidate


def _finalize_status(candidate):
    flags = candidate.pop("_flags")
    chosen = candidate.pop("_chosen")
    scale = candidate["scale"]
    issues = candidate["issues"]
    all_linked = bool(chosen) and all(d["linked_to_contour"] for d in candidate["dimensions"])
    label = candidate["boundary"]["label"]
    values = [chosen[o]["value_mm"] for o in ("H", "V") if o in chosen]

    if candidate["shape"] != "rectangle":
        issues.append("Kontūra nav taisnstūris (L/U vai cita forma): automātiska sadalīšana netiek veikta; "
                      "ievadi atsevišķus taisnstūrus manuāli.")
        status = REFUSED
    elif scale["status"] == "pretrunā":
        issues.append("Mēroga pretruna: L un W netiek piedāvāti; pārbaudi mērogu rasējumā.")
        status = REFUSED
    elif len(values) < 2:
        issues.append("Nav abu izmēru norāžu, kas sakristu ar kontūras malām: L un W nav nosakāmi.")
        status = UNCLEAR
    else:
        if flags["nested_ambiguous"]:
            issues.append("Ligzdotas kontūras bez moduļa marķējuma: nav pierādīts, kura ir grīdas rāmja robeža "
                          "(var būt fasādes kontūra).")
        if flags["role_conflict"]:
            issues.append("Kontūrā ir gan moduļa, gan telpas/terases marķējums.")
        # katra kopējā mala jāmarķē atsevišķi: viena marķēta mala nepadara neskaidru otru
        adjacency_open = any(n["separator"] is None for n in candidate["boundary"]["neighbours"])
        clean = (scale["status"] == "pārbaudīts" and all_linked and not flags["nested_ambiguous"]
                 and not flags["role_conflict"] and not adjacency_open
                 and not any("pretrunīgas" in i for i in issues))
        if clean and label:
            status = CONSISTENT
        elif clean:
            status = RECOGNISED
            issues.append("Nav pierādīts, ka šī kontūra ir grīdas rāmja robeža (var būt fasādes kontūra): "
                          "nav moduļa marķējuma.")
        else:
            status = UNCLEAR
    candidate["status"] = status
    if status in TRANSFERABLE and len(values) == 2:
        candidate["length_mm"], candidate["width_mm"] = max(values), min(values)
        candidate["transferable"] = True
        horizontal = chosen["H"]["value_mm"] >= chosen["V"]["value_mm"]
        candidate["orientation"] = "horizontāla" if horizontal else "vertikāla"
        candidate["evidence"].append(
            f"L = {max(values)} mm, W = {min(values)} mm (no izmēru norādēm; garākā mala ir "
            f"{candidate['orientation']}).")


# --- PDF līmeņa ieeja un priekšskatījums -------------------------------------------------------
def analyze_pdf(data: bytes, pages):
    """Analizē norādītās lapas (1-based). Atgriež {"pages": [...]}; kļūdas lapā neaptur pārējās."""
    results = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for number in pages:
            if not 1 <= number <= len(doc):
                continue
            try:
                results.append(analyze_page(doc[number - 1], number))
            except Exception as error:  # prototips: neapstādina visu analīzi
                results.append({"page": number, "status": "error", "candidates": [], "excluded": [],
                                "dimensions": [], "scale": None, "notes": [f"Analīzes kļūda: {error}"]})
    return {"pages": results}


STATUS_COLORS = {CONSISTENT: (0.10, 0.60, 0.25), RECOGNISED: (0.20, 0.60, 0.20),
                 UNCLEAR: (0.95, 0.55, 0.05), REFUSED: (0.85, 0.10, 0.10)}


def _overlay_text(page, point, text, size, color):
    """Unicode teksts (garumzīmes) pārklājumam; insert_text tās nekodē."""
    writer = pymupdf.TextWriter(page.rect)
    writer.append(point, text, font=pymupdf.Font("helv"), fontsize=size)
    writer.write_text(page, color=color)


def render_preview_png(data: bytes, analysis: dict, selected_id=None, dpi=72):
    """Lapas attēls ar iezīmētām kontūrām, izmēru norādēm un avotu. Zīmē analīzes (nerotētajās) koordinātēs."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        page = doc[analysis["page"] - 1]
        for item in analysis.get("excluded", []):
            if item["kind"] in ("page_frame", "unmeasured"):
                continue
            rect = pymupdf.Rect(*item["bbox"])
            page.draw_rect(rect, color=(0.5, 0.5, 0.5), width=1.5, dashes="[4 3] 0")
            _overlay_text(page, (rect.x0 + 3, rect.y0 - 3), f"izslēgts: {item['kind']}", 8, (0.4, 0.4, 0.4))
        for dim in analysis.get("dimensions", []):
            rect = pymupdf.Rect(*dim["text_bbox"])
            page.draw_rect(rect + (-1, -1, 1, 1), color=(0.1, 0.3, 0.9), width=0.8)
        for cand in analysis.get("candidates", []):
            color = STATUS_COLORS[cand["status"]]
            selected = cand["id"] == selected_id
            points = [tuple(p) for p in cand["vertices_pt"]]
            page.draw_polyline(points + [points[0]], color=color, width=4.0 if selected else 2.5,
                               fill=color if selected else None, fill_opacity=0.12 if selected else 1)
            size = f"{cand['length_mm']}×{cand['width_mm']}" if cand["length_mm"] else "L/W nav"
            x0, y0 = cand["bbox_pt"][0], cand["bbox_pt"][1]
            _overlay_text(page, (x0 + 6, y0 + 15), f"{cand['id']} {size} ({cand['status']})", 11, color)
            for dim in cand["dimensions"]:
                rect = pymupdf.Rect(*dim["text_bbox_pt"])
                page.draw_rect(rect + (-2, -2, 2, 2), color=color, width=1.6)
        return page.get_pixmap(dpi=dpi).tobytes("png")
