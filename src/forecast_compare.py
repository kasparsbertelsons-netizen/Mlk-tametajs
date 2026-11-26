"""AD prognozes versijas, faktiskā salīdzināšana un kalibrētā versija (Issue #16). Tikai lokāli; nekādi uzņēmuma dati kodā.

Principi:
- **Prognozes versija tiek FIKSĒTA pirms salīdzināšanas** (`freeze_forecast`): nemainīgs momentuzņēmums (rindas, stundas, budžets, pirkstu nospiedums).
  Salīdzināšana lieto MOMENTUZŅĒMUMU, nevis dzīvo tāmi; faktiskie dati nekad neaizpilda un nepārraksta AD prognozi.
- Salīdzina TIKAI vienādu izmaksu tvērumu: materiāli ↔ materiāli, ārējās izmaksas ↔ ārējās izmaksas, stundas ↔ stundas. Citādi — «nav salīdzināms».
- Mērvienības netiek konvertētas: atšķirīgas vienības → «mērvienība neatbilst».
- EUR starpība = faktiskais − prognoze (pozitīva = pārtēriņš); absolūtā procentu novirze = |prognoze − fakts| / |fakts| × 100 (fakts 0 → nav definēta).
- Kalibrētā versija ir ATSEVIŠĶA projekta kopija (`make_derived_project`); AD projekts un tā momentuzņēmums paliek nemainīgi.
"""
import copy
import math
from dataclasses import dataclass, field

from src.building_estimate import GROUPS, ST_DUP, norm_name, project_fingerprint
from src.control_import import SCOPE_EXTERNAL, SCOPE_HOURS, SCOPE_MATERIAL, ControlSheet, HoursReport

NO_STAGE = "(posms nav norādīts)"
STAGES = {"AD": "AD prognoze (sākotnējā)", "PD": "PD detalizācija (vēlāk)", "kalibrēta": "Kalibrētā versija"}


def forecast_scope(row) -> str:
    return {"materiāli": SCOPE_MATERIAL, "materiāli+montāža": "materiāli+montāža", "ārpakalpojums": SCOPE_EXTERNAL}.get(row.cost_scope, SCOPE_MATERIAL)


def freeze_forecast(project: dict, est, label: str, *, created: str = "") -> dict:
    """Atgriež NEMAINĪGU prognozes momentuzņēmumu (JSON-drošs dict). Pievienošana projektam: `add_version`."""
    b = est.budget()
    rows = [{"row_id": r.row_id, "group": r.group, "article": r.article or "", "material": r.material, "spec": r.spec, "unit": r.unit,
             "qty": r.qty, "order_qty": r.order_qty, "unit_price": r.unit_price, "cost": r.cost, "scope": forecast_scope(r), "stage": r.stage,
             "module": r.module, "detail": r.detail, "assumption": r.assumption}
            for r in est.rows if r.status != ST_DUP and r.qty is not None]
    labour = [{"row_id": x.row_id, "group": x.group, "name": x.name, "stage": x.stage, "module": x.module, "hours": x.hours, "cost": x.cost}
              for x in est.labour if x.hours is not None]
    others = [{"name": n, "category": i["category"], "amount": i["amount"], "scope": SCOPE_EXTERNAL} for (n, _a), i in zip(est.other_costs, est.cost_items)]
    keys = ("materials", "labour_hours", "labour_cost", "other", "direct", "overhead", "cost_total", "sell", "vat", "total_incl", "incomplete")
    return {"id": "v" + project_fingerprint(project)[:10], "kind": "AD", "label": str(label or "AD prognoze")[:80], "created": created,
            "fingerprint": project_fingerprint(project), "locked": True, "budget": {k: b[k] for k in keys}, "budget_reasons": list(b["reasons"]),
            "rows": rows, "labour": labour, "other_costs": others}


def add_version(project: dict, snapshot: dict) -> dict:
    """Pievieno momentuzņēmumu; esošs ar to pašu ID netiek pārrakstīts (nemainīgs)."""
    versions = project.setdefault("versions", [])
    if any(v.get("id") == snapshot["id"] for v in versions):
        return next(v for v in versions if v["id"] == snapshot["id"])
    versions.append(snapshot)
    return snapshot


def get_version(project, version_id):
    return next((v for v in project.get("versions") or [] if v.get("id") == version_id), None)


@dataclass
class Compare:
    version_id: str = ""
    material_lines: list = field(default_factory=list)      # saistītās rindas (artikuls + izmaksu segums), AGREGĒTAS
    external_lines: list = field(default_factory=list)
    uncomparable: list = field(default_factory=list)        # (iemesls, apraksts)
    unmatched_actual: list = field(default_factory=list)    # faktiskās rindas bez prognozes rindas
    unmatched_forecast: list = field(default_factory=list)  # prognozes rindas bez faktiskās
    hours: list = field(default_factory=list)               # pa posmiem
    group_abs_dev: dict = field(default_factory=dict)       # grupa → absolūto noviržu summa (EUR), tikai saistītās rindas
    totals: dict = field(default_factory=dict)              # SASAISTĪTO rindu kopsummas (materials_*, external_*, hours_*)
    scope_totals: dict = field(default_factory=dict)        # VISA izmaksu tvēruma kopsummas (ar nesasaistītajām rindām) + pārklājums
    notes: list = field(default_factory=list)


def _pct(forecast, actual):
    if forecast is None or actual is None or actual == 0:
        return None
    return abs(forecast - actual) / abs(actual) * 100.0


def _actual_sum(l):
    if l.actual_sum is not None:
        return l.actual_sum
    if l.actual_qty is not None and l.actual_price is not None:
        return l.actual_qty * l.actual_price
    return None


def _stage_label(l):
    return str(getattr(l, "stage", "") or "").strip()


def _aggregate_actual(lines):
    """Vienam artikulam+segumam visas faktiskās rindas (arī no vairākiem posmiem) tiek AGREGĒTAS; avota rindas saglabātas `sources`."""
    units = {l.unit for l in lines}
    qtys = [l.actual_qty for l in lines]
    sums = [_actual_sum(l) for l in lines]
    prices = {l.actual_price for l in lines if l.actual_price is not None}
    unit = next(iter(units)) if len(units) == 1 else "?"
    issues = []
    qty = sum(q for q in qtys if q is not None) if all(q is not None for q in qtys) else None
    if len(units) > 1:
        issues.append("faktiskajām rindām atšķiras mērvienības: daudzums nav summējams")
        qty = None
    total = sum(x for x in sums if x is not None) if all(x is not None for x in sums) else None
    if total is None:
        issues.append("dažām faktiskajām rindām nav summas")
    return {"unit": None if unit in (None, "?") else unit, "unit_mixed": len(units) > 1, "qty": qty, "sum": total, "known_sum": sum(x for x in sums if x is not None),
            "price": next(iter(prices)) if len(prices) == 1 else None, "issues": issues,
            "sources": [{"row_no": l.row_no, "stage": _stage_label(l), "qty": l.actual_qty, "price": l.actual_price, "sum": _actual_sum(l),
                         "plan_qty": l.plan_qty, "plan_sum": l.plan_sum} for l in lines]}


def compare_to_actual(snapshot: dict, sheet: ControlSheet, *, default_scope=None) -> Compare:
    """Salīdzina FIKSĒTO prognozi ar importēto kontroltāmi. Gan prognoze, gan fakts vispirms tiek AGREGĒTI pa artikulu+izmaksu tvērumu (artikuls, kas
    izmantots vairākos posmos, netiek dubultots); posmu sadalījums tiek dots tikai tad, ja abām pusēm ir saderīga posmu piesaiste. Atsevišķi tiek
    uzrādītas VISA tvēruma kopsummas (ar nesasaistītajām rindām) un pārklājums: sasaistīto rindu novirze NAV visas ēkas precizitāte.
    `default_scope` — lietotāja skaidra izvēle rindām bez izmaksu seguma (None = tādas rindas netiek salīdzinātas)."""
    out = Compare(version_id=snapshot.get("id", ""))
    if not snapshot.get("locked"):
        out.notes.append("Prognozes versija nav fiksēta: salīdzināšana nav atļauta.")
        return out
    by_art, scope_f = {}, {}
    for r in snapshot["rows"]:
        f = scope_f.setdefault(r["scope"], {"forecast_total": 0.0, "forecast_unpriced_rows": 0, "forecast_rows": 0})
        f["forecast_rows"] += 1
        if r["cost"] is None:
            f["forecast_unpriced_rows"] += 1
        else:
            f["forecast_total"] += r["cost"]
        if r["article"]:
            by_art.setdefault((r["article"], r["scope"]), []).append(r)
    noart = [r for r in snapshot["rows"] if not r["article"]]
    if noart:
        out.notes.append(f"{len(noart)} prognozes rindām nav artikula: tās nav saistāmas ar kontroltāmi (ievadi artikulus).")
    actual_groups, scope_a, uncomparable_sum, all_actual = {}, {}, 0.0, 0.0
    for l in sheet.items:
        scope = l.scope or default_scope
        a_sum = _actual_sum(l)
        all_actual += a_sum or 0.0
        label = f"{l.code} {l.name}".strip()
        if scope is None:
            out.uncomparable.append(("izmaksu segums nav norādīts", label))
            uncomparable_sum += a_sum or 0.0
            continue
        actual_groups.setdefault((l.code, scope), []).append(l)
        sc = scope_a.setdefault(scope, {"actual_total": 0.0, "actual_unknown_rows": 0})
        if a_sum is None:
            sc["actual_unknown_rows"] += 1
        else:
            sc["actual_total"] += a_sum
    matched_keys = set()
    matched_sums = {}
    unmatched_a_sum, unmatched_f_sum = {}, {}
    for (code, scope), lines in actual_groups.items():
        agg = _aggregate_actual(lines)
        name = lines[0].name
        label = f"{code} {name}".strip()
        rows = by_art.get((code, scope))
        if not rows:
            other = [k for k in by_art if k[0] == code]
            if other:
                out.uncomparable.append((f"izmaksu segums atšķiras (prognoze: {other[0][1]}, fakts: {scope})", label))
                uncomparable_sum += agg["known_sum"]
                scope_a[scope]["actual_total"] -= agg["known_sum"]            # šis fakts nav šī seguma salīdzināmajā tvērumā
            else:
                out.unmatched_actual.append({"code": code, "name": name, "scope": scope, "unit": agg["unit"], "actual_qty": agg["qty"],
                                             "actual_sum": agg["sum"], "stage": ", ".join(sorted({x["stage"] for x in agg["sources"] if x["stage"]})),
                                             "sources": agg["sources"]})
                unmatched_a_sum[scope] = unmatched_a_sum.get(scope, 0.0) + agg["known_sum"]
            continue
        matched_keys.add((code, scope))
        units = {r["unit"] for r in rows}
        f_qty = sum(r["order_qty"] for r in rows if r["order_qty"] is not None)
        f_sum_parts = [r["cost"] for r in rows]
        f_sum = None if any(c is None for c in f_sum_parts) else sum(f_sum_parts)
        a_sum = agg["sum"]
        line = {"code": code, "name": name, "scope": scope, "stage": ", ".join(sorted({x["stage"] for x in agg["sources"] if x["stage"]})),
                "group": rows[0]["group"], "forecast_unit": "/".join(sorted(units)), "actual_unit": agg["unit"], "forecast_qty": f_qty,
                "actual_qty": agg["qty"], "forecast_sum": f_sum, "actual_sum": a_sum,
                "forecast_price": (rows[0]["unit_price"] if len({r["unit_price"] for r in rows}) == 1 else None), "actual_price": agg["price"],
                "plan_qty_sheet": sum(x["plan_qty"] for x in agg["sources"] if x["plan_qty"] is not None) or None,
                "plan_sum_sheet": sum(x["plan_sum"] for x in agg["sources"] if x["plan_sum"] is not None) or None,
                "issues": list(agg["issues"]), "sources": agg["sources"], "forecast_rows": len(rows), "actual_rows": len(lines)}
        if len(lines) > 1:
            line["issues"].append(f"faktiskās rindas no {len(lines)} posmiem/rindām AGREGĒTAS (prognoze nav dubultota)")
        if agg["unit"] is None:
            line["issues"].append("faktiskajai rindai nav mērvienības (netiek izdomāta): daudzums nav salīdzināms")
            line["qty_comparable"] = False
        elif agg["unit_mixed"] or len(units) != 1 or agg["unit"] not in units:
            line["issues"].append(f"mērvienība neatbilst (prognoze {line['forecast_unit']}, fakts {agg['unit']}): daudzums nav salīdzināms; konversijas netiek veiktas")
            line["qty_comparable"] = False
        else:
            line["qty_comparable"] = True
        line["qty_diff"] = (agg["qty"] - f_qty) if line["qty_comparable"] and agg["qty"] is not None else None
        line["qty_abs_pct"] = _pct(f_qty, agg["qty"]) if line["qty_comparable"] else None
        if f_sum is None:
            line["issues"].append("prognozei nav cenas: EUR starpība nav aprēķināma")
        line["diff_eur"] = (a_sum - f_sum) if f_sum is not None and a_sum is not None else None
        line["abs_pct"] = _pct(f_sum, a_sum) if line["diff_eur"] is not None else None
        line["by_stage"] = _by_stage(rows, lines)
        if line["by_stage"] is None and (len(lines) > 1 or any(r["stage"] for r in rows)):
            line["issues"].append("posmu piesaiste nav saderīga abām pusēm: salīdzināts pa artikulu, nevis pa posmiem")
        if line["diff_eur"] is not None:
            m = matched_sums.setdefault(scope, {"f": 0.0, "a": 0.0})
            m["f"] += f_sum
            m["a"] += a_sum
        (out.material_lines if scope == SCOPE_MATERIAL else out.external_lines).append(line)
    for r in noart:                                                    # rindas bez artikula nav saistāmas: skaitās nesasaistītajā prognozē (tvēruma kopsumma nezūd)
        if r["cost"] is not None:
            unmatched_f_sum[r["scope"]] = unmatched_f_sum.get(r["scope"], 0.0) + r["cost"]
    for (code, scope), rows in by_art.items():
        if (code, scope) not in matched_keys:
            known = sum(r["cost"] for r in rows if r["cost"] is not None)
            out.unmatched_forecast.append({"code": code, "scope": scope, "name": rows[0]["material"], "forecast_qty": sum(r["order_qty"] or 0 for r in rows),
                                           "forecast_sum": None if any(r["cost"] is None for r in rows) else sum(r["cost"] for r in rows),
                                           "group": rows[0]["group"]})
            unmatched_f_sum[scope] = unmatched_f_sum.get(scope, 0.0) + known
    for line in out.material_lines + out.external_lines:
        if line["diff_eur"] is not None:
            out.group_abs_dev[line["group"]] = out.group_abs_dev.get(line["group"], 0.0) + abs(line["diff_eur"])
    # stundas pa posmiem (vispārīgajam kontroltāmes formātam)
    f_hours, label_of = {}, {}
    for x in snapshot["labour"]:
        key = norm_name(x["stage"]) or NO_STAGE
        label_of.setdefault(key, x["stage"] or NO_STAGE)
        f_hours[key] = f_hours.get(key, 0.0) + x["hours"]
    a_hours, a_plan = {}, {}
    for h in sheet.hours:
        key = norm_name(h.stage) or NO_STAGE
        label_of.setdefault(key, h.stage or NO_STAGE)
        if h.actual_qty is not None:
            a_hours[key] = a_hours.get(key, 0.0) + h.actual_qty
        if h.plan_qty is not None:
            a_plan[key] = a_plan.get(key, 0.0) + h.plan_qty
    for key in sorted(set(f_hours) | set(a_hours)):
        fh, ah = f_hours.get(key), a_hours.get(key)
        out.hours.append({"stage": label_of.get(key, key), "forecast_hours": fh, "actual_hours": ah, "sheet_plan_hours": a_plan.get(key),
                          "diff_h": None if fh is None or ah is None else ah - fh, "abs_pct": _pct(fh, ah),
                          "note": "" if fh is not None and ah is not None else "posms ir tikai vienā pusē (nesaistīts)"})
    mat = matched_sums.get(SCOPE_MATERIAL, {"f": 0.0, "a": 0.0})
    ext = matched_sums.get(SCOPE_EXTERNAL, {"f": 0.0, "a": 0.0})
    out.totals = {"materials_forecast": mat["f"], "materials_actual": mat["a"], "materials_diff": mat["a"] - mat["f"], "materials_abs_pct": _pct(mat["f"], mat["a"]),
                  "external_forecast": ext["f"], "external_actual": ext["a"], "external_diff": ext["a"] - ext["f"], "external_abs_pct": _pct(ext["f"], ext["a"]),
                  "abs_dev_total": sum(out.group_abs_dev.values()),
                  "hours_forecast": sum(h["forecast_hours"] for h in out.hours if h["diff_h"] is not None),
                  "hours_actual": sum(h["actual_hours"] for h in out.hours if h["diff_h"] is not None),
                  "uncomparable_actual_sum": uncomparable_sum, "all_actual_items_sum": all_actual}
    out.totals["hours_diff"] = out.totals["hours_actual"] - out.totals["hours_forecast"]
    out.totals["hours_abs_pct"] = _pct(out.totals["hours_forecast"], out.totals["hours_actual"])
    for scope in sorted(set(scope_f) | set(scope_a)):
        f = scope_f.get(scope, {"forecast_total": 0.0, "forecast_unpriced_rows": 0, "forecast_rows": 0})
        a = scope_a.get(scope, {"actual_total": 0.0, "actual_unknown_rows": 0})
        m = matched_sums.get(scope, {"f": 0.0, "a": 0.0})
        out.scope_totals[scope] = {
            **f, **a, "matched_forecast": m["f"], "matched_actual": m["a"], "unmatched_forecast": unmatched_f_sum.get(scope, 0.0),
            "unmatched_actual": unmatched_a_sum.get(scope, 0.0), "diff_total": a["actual_total"] - f["forecast_total"],
            "abs_pct_total": _pct(f["forecast_total"], a["actual_total"]),
            "coverage_actual_pct": (m["a"] / a["actual_total"] * 100.0) if a["actual_total"] else None,
            "coverage_forecast_pct": (m["f"] / f["forecast_total"] * 100.0) if f["forecast_total"] else None}
    return out


def _by_stage(rows, lines):
    """Pa posmiem tikai tad, ja KATRAI prognozes un faktiskajai rindai ir posms; citādi None (salīdzina pa artikulu kopā)."""
    if not all(r["stage"] for r in rows) or not all(_stage_label(l) for l in lines):
        return None
    f, a = {}, {}
    labels = {}
    for r in rows:
        k = norm_name(r["stage"])
        labels.setdefault(k, r["stage"])
        f[k] = (f.get(k) or 0.0) + (r["cost"] or 0.0)
    for l in lines:
        k = norm_name(_stage_label(l))
        labels.setdefault(k, _stage_label(l))
        a[k] = (a.get(k) or 0.0) + (_actual_sum(l) or 0.0)
    return [{"stage": labels[k], "forecast_sum": f.get(k), "actual_sum": a.get(k), "diff_eur": None if k not in f or k not in a else a[k] - f[k],
             "note": "" if k in f and k in a else "posms ir tikai vienā pusē"} for k in sorted(set(f) | set(a))]


# --- stundas pa OPERĀCIJĀM (Moneo stundu pārskats): prognozes darba operācijas ↔ faktiskās operācijas -----------------------------------------------
@dataclass
class HoursCompare:
    lines: list = field(default_factory=list)                # saistītās operācijas (agregētas)
    unmatched_actual: list = field(default_factory=list)
    unmatched_forecast: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)               # sasaistītais un VISA tvēruma kopsummas
    notes: list = field(default_factory=list)


def compare_hours_by_operation(snapshot: dict, report: HoursReport, mapping=None) -> HoursCompare:
    """Salīdzina FIKSĒTĀS prognozes darba operāciju stundas ar stundu pārskatu. Sasaiste pēc normalizēta nosaukuma; atšķirīgus nosaukumus lietotājs kartē
    (`mapping`: faktiskās operācijas nosaukums → prognozes operācijas nosaukums). Atkārtotas operācijas tiek agregētas (prognoze netiek dubultota)."""
    out = HoursCompare()
    mapping = {norm_name(k): norm_name(v) for k, v in (mapping or {}).items() if v}
    if not snapshot.get("locked"):
        out.notes.append("Prognozes versija nav fiksēta: salīdzināšana nav atļauta.")
        return out
    forecast = {}
    for x in snapshot["labour"]:
        k = norm_name(x["name"])
        f = forecast.setdefault(k, {"name": x["name"], "hours": 0.0, "group": x["group"], "stage": x["stage"]})
        f["hours"] += x["hours"]
    actual = {}
    for o in report.operations:
        k = mapping.get(norm_name(o.name), norm_name(o.name))
        a = actual.setdefault(k, {"names": [], "actual": 0.0, "plan": 0.0, "actual_known": True, "plan_known": True, "sources": []})
        a["names"].append(o.name)
        if o.actual is None:
            a["actual_known"] = False
        else:
            a["actual"] += o.actual
        if o.plan is None:
            a["plan_known"] = False
        else:
            a["plan"] += o.plan
        a["sources"].append({"row_no": o.row_no, "name": o.name, "actual": o.actual, "plan": o.plan})
    matched_f = matched_a = 0.0
    for k, a in actual.items():
        f = forecast.get(k)
        act = a["actual"] if a["actual_known"] else None
        if f is None:
            out.unmatched_actual.append({"name": a["names"][0], "actual": act, "plan": a["plan"] if a["plan_known"] else None, "sources": a["sources"]})
            continue
        line = {"name": f["name"], "actual_names": sorted(set(a["names"])), "group": f["group"], "forecast_hours": f["hours"], "actual_hours": act,
                "sheet_plan_hours": a["plan"] if a["plan_known"] else None, "diff_h": None if act is None else act - f["hours"],
                "abs_pct": _pct(f["hours"], act), "sources": a["sources"],
                "issues": ["faktiskās rindas AGREGĒTAS (prognoze nav dubultota)"] if len(a["sources"]) > 1 else []}
        out.lines.append(line)
        if act is not None:
            matched_f += f["hours"]
            matched_a += act
    for k, f in forecast.items():
        if k not in actual:
            out.unmatched_forecast.append({"name": f["name"], "forecast_hours": f["hours"], "group": f["group"]})
    all_f = sum(f["hours"] for f in forecast.values())
    all_a = sum(a["actual"] for a in actual.values() if a["actual_known"])
    un_a = sum(u["actual"] or 0.0 for u in out.unmatched_actual)
    un_f = sum(u["forecast_hours"] for u in out.unmatched_forecast)
    out.totals = {"matched_forecast": matched_f, "matched_actual": matched_a, "matched_diff": matched_a - matched_f, "matched_abs_pct": _pct(matched_f, matched_a),
                  "all_forecast": all_f, "all_actual": all_a, "all_diff": all_a - all_f, "all_abs_pct": _pct(all_f, all_a),
                  "unmatched_actual_hours": un_a, "unmatched_forecast_hours": un_f,
                  "coverage_actual_pct": (matched_a / all_a * 100.0) if all_a else None, "coverage_forecast_pct": (matched_f / all_f * 100.0) if all_f else None,
                  "control_total_actual": report.total_actual, "control_total_plan": report.total_plan}
    return out


# --- kalibrētā / PD versija: ATSEVIŠĶA kopija ---------------------------------------------------------------------------
def suggest_calibration(cmp: Compare):
    """Kalibrēšanas priekšlikumi no saistītajām materiālu rindām: faktiskā cena par artikulu (ja vienības sakrīt) un daudzuma koeficients."""
    out = []
    for l in cmp.material_lines:
        if l["actual_price"] is not None and l["forecast_price"] is not None and l["actual_unit"] == l["forecast_unit"] \
                and abs(l["actual_price"] - l["forecast_price"]) > 1e-9:
            out.append({"article": l["code"], "field": "unit_price", "old": l["forecast_price"], "new": l["actual_price"],
                        "label": f"{l['code']} cena {l['forecast_price']:g} → {l['actual_price']:g} EUR/{l['actual_unit']}"})
        if l.get("qty_comparable") and l["actual_qty"] and l["forecast_qty"]:
            factor = l["actual_qty"] / l["forecast_qty"]
            if abs(factor - 1) > 1e-9:
                out.append({"article": l["code"], "field": "norm_factor", "old": 1.0, "new": factor,
                            "label": f"{l['code']} patēriņa koeficients ×{factor:.4f} (fakts/prognoze)"})
    return out


def make_derived_project(project: dict, *, stage: str, label: str, snapshot_id: str = "", suggestions=()) -> dict:
    """Atsevišķa projekta kopija (kalibrētā vai PD versija). AD projekts, tā versijas un faktiskie dati netiek mainīti.
    `suggestions`: apstiprinātie kalibrēšanas priekšlikumi (cenas katalogā, normas receptēs ar normu)."""
    if stage not in STAGES or stage == "AD":
        raise ValueError("Atvasinātā versija var būt tikai «kalibrēta» vai «PD».")
    new = copy.deepcopy(project)
    new["stage"] = stage
    new["name"] = f"{project.get('name') or 'Projekts'} — {label}"[:80]
    new["versions"] = []                      # kopija neiekļauj AD momentuzņēmumus vai faktiskos datus (tie paliek AD projektā)
    new["actuals"] = None
    new["review"] = {"reviewer": "", "confirmed": False, "fp": None}
    new["derived_from"] = {"project": project.get("name"), "snapshot": snapshot_id, "fingerprint": project_fingerprint(project)}
    applied = []
    for s in suggestions:
        if s["field"] == "unit_price":
            for c in new.get("catalog") or []:
                if str(c.get("article")) == s["article"]:
                    c["unit_price"] = s["new"]
                    applied.append(s["label"])
        elif s["field"] == "norm_factor":
            for key in ("recipes", "type_recipes"):
                for r in new.get(key) or []:
                    if str(r.get("article") or "") == s["article"] and r.get("norm") not in (None, 0):
                        r["norm"] = r["norm"] * s["new"]
                        applied.append(s["label"])
    new["derived_from"]["applied"] = applied
    return new
