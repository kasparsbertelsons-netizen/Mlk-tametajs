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
from src.control_import import SCOPE_EXTERNAL, SCOPE_HOURS, SCOPE_MATERIAL, ControlSheet

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
    material_lines: list = field(default_factory=list)      # saistītās rindas (artikuls)
    external_lines: list = field(default_factory=list)
    uncomparable: list = field(default_factory=list)        # (iemesls, apraksts)
    unmatched_actual: list = field(default_factory=list)    # faktiskās rindas bez prognozes rindas
    unmatched_forecast: list = field(default_factory=list)  # prognozes rindas bez faktiskās
    hours: list = field(default_factory=list)               # pa posmiem
    group_abs_dev: dict = field(default_factory=dict)       # grupa → absolūto noviržu summa (EUR)
    totals: dict = field(default_factory=dict)
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


def compare_to_actual(snapshot: dict, sheet: ControlSheet, *, default_scope=None) -> Compare:
    """Salīdzina FIKSĒTO prognozi ar importēto kontroltāmi. `default_scope` — lietotāja skaidra izvēle rindām, kurām eksportā nav izmaksu seguma
    (None = tādas rindas netiek salīdzinātas)."""
    out = Compare(version_id=snapshot.get("id", ""))
    if not snapshot.get("locked"):
        out.notes.append("Prognozes versija nav fiksēta: salīdzināšana nav atļauta.")
        return out
    # prognozes rindas pa artikuliem (tikai ar artikulu; rindas bez artikula nav saistāmas)
    by_art = {}
    for r in snapshot["rows"]:
        if r["article"]:
            by_art.setdefault((r["article"], r["scope"]), []).append(r)
    noart = [r for r in snapshot["rows"] if not r["article"]]
    if noart:
        out.notes.append(f"{len(noart)} prognozes rindām nav artikula: tās nav saistāmas ar kontroltāmi (ievadi artikulus).")
    matched_keys = set()
    for l in sheet.items:
        scope = l.scope or default_scope
        label = f"{l.code} {l.name}".strip()
        if scope is None:
            out.uncomparable.append(("izmaksu segums nav norādīts", label))
            continue
        rows = by_art.get((l.code, scope))
        if not rows:
            other = [k for k in by_art if k[0] == l.code]
            if other:
                out.uncomparable.append((f"izmaksu segums atšķiras (prognoze: {other[0][1]}, fakts: {scope})", label))
            else:
                out.unmatched_actual.append({"code": l.code, "name": l.name, "scope": scope, "unit": l.unit, "actual_qty": l.actual_qty,
                                             "actual_sum": _actual_sum(l), "stage": l.stage})
            continue
        matched_keys.add((l.code, scope))
        units = {r["unit"] for r in rows}
        f_qty = sum(r["order_qty"] for r in rows if r["order_qty"] is not None)
        f_sum_parts = [r["cost"] for r in rows]
        f_sum = None if any(c is None for c in f_sum_parts) else sum(f_sum_parts)
        a_sum = _actual_sum(l)
        line = {"code": l.code, "name": l.name, "scope": scope, "stage": l.stage, "group": rows[0]["group"], "forecast_unit": "/".join(sorted(units)),
                "actual_unit": l.unit, "forecast_qty": f_qty, "actual_qty": l.actual_qty, "forecast_sum": f_sum, "actual_sum": a_sum,
                "forecast_price": (rows[0]["unit_price"] if len({r["unit_price"] for r in rows}) == 1 else None), "actual_price": l.actual_price,
                "plan_qty_sheet": l.plan_qty, "plan_sum_sheet": l.plan_sum, "issues": []}
        if l.unit is None:
            line["issues"].append("faktiskajai rindai nav mērvienības (netiek izdomāta): daudzums nav salīdzināms")
            line["qty_comparable"] = False
        elif len(units) != 1 or l.unit not in units:
            line["issues"].append(f"mērvienība neatbilst (prognoze {line['forecast_unit']}, fakts {l.unit}): daudzums nav salīdzināms; konversijas netiek veiktas")
            line["qty_comparable"] = False
        else:
            line["qty_comparable"] = True
        line["qty_diff"] = (l.actual_qty - f_qty) if line["qty_comparable"] and l.actual_qty is not None else None
        line["qty_abs_pct"] = _pct(f_qty, l.actual_qty) if line["qty_comparable"] else None
        if f_sum is None:
            line["issues"].append("prognozei nav cenas: EUR starpība nav aprēķināma")
        line["diff_eur"] = (a_sum - f_sum) if f_sum is not None and a_sum is not None else None
        line["abs_pct"] = _pct(f_sum, a_sum) if line["diff_eur"] is not None else None
        (out.material_lines if scope == SCOPE_MATERIAL else out.external_lines).append(line)
    for (code, scope), rows in by_art.items():
        if (code, scope) not in matched_keys:
            out.unmatched_forecast.append({"code": code, "scope": scope, "name": rows[0]["material"], "forecast_qty": sum(r["order_qty"] or 0 for r in rows),
                                           "forecast_sum": None if any(r["cost"] is None for r in rows) else sum(r["cost"] for r in rows),
                                           "group": rows[0]["group"]})
    # noviržu summas pa grupām (absolūtās EUR starpības)
    for line in out.material_lines + out.external_lines:
        if line["diff_eur"] is not None:
            out.group_abs_dev[line["group"]] = out.group_abs_dev.get(line["group"], 0.0) + abs(line["diff_eur"])
    # stundas pa posmiem: plāns (prognoze) pret faktu
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
    mat_f = sum(l["forecast_sum"] for l in out.material_lines if l["forecast_sum"] is not None and l["diff_eur"] is not None)
    mat_a = sum(l["actual_sum"] for l in out.material_lines if l["actual_sum"] is not None and l["diff_eur"] is not None)
    ext_f = sum(l["forecast_sum"] for l in out.external_lines if l["forecast_sum"] is not None and l["diff_eur"] is not None)
    ext_a = sum(l["actual_sum"] for l in out.external_lines if l["actual_sum"] is not None and l["diff_eur"] is not None)
    out.totals = {"materials_forecast": mat_f, "materials_actual": mat_a, "materials_diff": mat_a - mat_f, "materials_abs_pct": _pct(mat_f, mat_a),
                  "external_forecast": ext_f, "external_actual": ext_a, "external_diff": ext_a - ext_f, "external_abs_pct": _pct(ext_f, ext_a),
                  "abs_dev_total": sum(out.group_abs_dev.values()),
                  "hours_forecast": sum(h["forecast_hours"] for h in out.hours if h["diff_h"] is not None),
                  "hours_actual": sum(h["actual_hours"] for h in out.hours if h["diff_h"] is not None)}
    out.totals["hours_diff"] = out.totals["hours_actual"] - out.totals["hours_forecast"]
    out.totals["hours_abs_pct"] = _pct(out.totals["hours_forecast"], out.totals["hours_actual"])
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
