"""Streamlit sadaļa «Prognozes versijas un faktiskā kontrole» (Issue #16): AD prognozes fiksēšana, lokāla kontroltāmes importēšana, salīdzināšana,
kalibrētā/PD versija kā ATSEVIŠĶA kopija. Faktiskie dati neaizpilda un nepārraksta AD prognozi."""
import csv
import datetime
import io

import streamlit as st

from src.control_import import SCOPE_MATERIAL, parse_control_sheet
from src.forecast_compare import (
    STAGES, add_version, compare_to_actual, freeze_forecast, get_version, make_derived_project, suggest_calibration,
)
from src.project_io import LOCAL_DATA_REMINDER, export_project

SHEET_KEY = "bp_control_sheet"               # sesijā: (fails kontrolsumma, ControlSheet)


def _eur(v):
    return None if v is None else round(v, 2)


def _pct(v):
    return None if v is None else round(v, 2)


def render_control(project, est, ver, key_project, key_ver):
    st.caption("1) FIKSĒ AD prognozi (nemainīgs momentuzņēmums) → 2) importē Moneo kontroltāmi (XLSX/CSV, lokāli) → 3) salīdzini. Salīdzina tikai vienādu "
               "izmaksu tvērumu (materiāli ↔ materiāli, ārējās izmaksas ↔ ārējās izmaksas, stundas ↔ stundas); mērvienības netiek konvertētas. "
               "Faktiskie dati NEAIZPILDA un NEPĀRRAKSTA AD prognozi. Kalibrētā versija ir atsevišķa kopija.")
    st.warning(LOCAL_DATA_REMINDER)
    versions = project.setdefault("versions", [])
    c1, c2 = st.columns([3, 1])
    label = c1.text_input("Prognozes versijas nosaukums", value="AD prognoze v1", key=f"bp_vlabel_{ver}", max_chars=80)
    if c2.button("Fiksēt AD prognozi", key=f"bp_freeze_{ver}", use_container_width=True):
        snap = freeze_forecast(project, est, label, created=datetime.datetime.now().isoformat(timespec="seconds"))
        existing = get_version(project, snap["id"])
        add_version(project, snap)
        st.session_state["bp_notice"] = (f"Prognoze «{snap['label']}» jau bija fiksēta (nemainīta)." if existing else
                                         f"AD prognoze «{snap['label']}» fiksēta (nemaināma). Pašizmaksa {snap['budget']['cost_total']:.2f} EUR.")
        st.rerun()
    if not versions:
        st.info("Nav fiksētas prognozes: salīdzināšana nav pieejama. Spied «Fiksēt AD prognozi» (pēc tāmes pabeigšanas).")
        return
    st.dataframe([{"ID": v["id"], "Nosaukums": v["label"], "Stadija": STAGES.get(v["kind"], v["kind"]), "Fiksēta": v.get("created"),
                   "Rindas": len(v["rows"]), "Pašizmaksa EUR": _eur(v["budget"]["cost_total"]), "Cena bez PVN EUR": _eur(v["budget"]["sell"]),
                   "Nepilna": "JĀ" if v["budget"]["incomplete"] else ""} for v in versions], hide_index=True, use_container_width=True)
    if project.get("stage") == "AD":
        current = est.fingerprint
        if all(v["fingerprint"] != current for v in versions):
            st.warning("Tāme ir mainīta pēc pēdējās fiksētās prognozes: salīdzināšana notiek ar FIKSĒTO versiju, nevis ar pašreizējo tāmi.")

    st.markdown("**Faktiskā kontroltāme (Moneo, sintētisks paraugs vai lokāli reāls)**")
    upload = st.file_uploader("Kontroltāme (.xlsx vai .csv)", type=["xlsx", "csv"], key=f"bp_ctrl_{ver}")
    if upload is None:
        st.session_state.pop(SHEET_KEY, None)
        return
    data = upload.getvalue()
    sheet = parse_control_sheet(upload.name, data)
    for row_no, message in sheet.errors:
        st.error((f"Rinda {row_no}: " if row_no else "") + message)
    for row_no, message in sheet.warnings[:20]:
        st.warning((f"Rinda {row_no}: " if row_no else "") + message)
    if sheet.fatal:
        return
    st.write(f"Nolasīts: artikulu rindas **{len(sheet.items)}**, stundu rindas **{len(sheet.hours)}**, kopsummu rindas {len(sheet.totals)} "
             "(kopsummas netiek summētas — tikai saskaņošanai).")
    if sheet.reconciliation:
        st.dataframe([{"Rinda": r["row_no"], "Kopsumma": r["label"], "Veids": r["type"], "Plāns (kopsumma)": r["total_plan"], "Plāns (Σ artikuli)": r["sum_plan"],
                       "Fakts (kopsumma)": r["total_actual"], "Fakts (Σ artikuli)": r["sum_actual"], "Saskan": "✓" if r["ok"] else "✗"}
                      for r in sheet.reconciliation], hide_index=True, use_container_width=True)
    choice = st.selectbox("Salīdzināmā prognozes versija", [f"{v['id']} — {v['label']}" for v in versions], key=f"bp_vsel_{ver}")
    snapshot = get_version(project, choice.split(" — ")[0])
    scope_choice = st.selectbox("Rindām bez norādīta izmaksu seguma", ["Nesalīdzināt (nav norādīts)", "Uzskatīt par materiāliem (mana izvēle)"],
                                key=f"bp_dscope_{ver}")
    cmp = compare_to_actual(snapshot, sheet, default_scope=SCOPE_MATERIAL if scope_choice.startswith("Uzskatīt") else None)
    t = cmp.totals
    m1, m2, m3 = st.columns(3)
    m1.metric("Materiāli: starpība (fakts − prognoze)", f"{t['materials_diff']:.2f} EUR", delta=None if t["materials_abs_pct"] is None else f"{t['materials_abs_pct']:.2f} % (abs.)")
    m2.metric("Ārējās izmaksas: starpība", f"{t['external_diff']:.2f} EUR", delta=None if t["external_abs_pct"] is None else f"{t['external_abs_pct']:.2f} % (abs.)")
    m3.metric("Stundas: starpība", f"{t['hours_diff']:.2f} h", delta=None if t["hours_abs_pct"] is None else f"{t['hours_abs_pct']:.2f} % (abs.)")
    st.caption(f"Absolūto EUR noviržu summa (visas saistītās rindas): {t['abs_dev_total']:.2f} EUR. Starpība = fakts − prognoze; novirze % = |prognoze − fakts| / |fakts|.")
    for title, lines in (("Materiāli (saistītās rindas)", cmp.material_lines), ("Ārējās izmaksas (saistītās rindas)", cmp.external_lines)):
        if lines:
            st.markdown(f"**{title}**")
            st.dataframe([{"Artikuls": l["code"], "Nosaukums": l["name"], "Grupa": l["group"], "Vienība (prog./fakts)": f"{l['forecast_unit']} / {l['actual_unit']}",
                           "Prognoze daudz.": None if l["forecast_qty"] is None else round(l["forecast_qty"], 3), "Fakts daudz.": l["actual_qty"],
                           "Prognoze EUR": _eur(l["forecast_sum"]), "Fakts EUR": _eur(l["actual_sum"]), "Starpība EUR": _eur(l["diff_eur"]),
                           "Novirze %": _pct(l["abs_pct"]), "Piezīmes": "; ".join(l["issues"])} for l in lines], hide_index=True, use_container_width=True)
    if cmp.group_abs_dev:
        st.markdown("**Absolūto noviržu summa pa grupām (EUR)**")
        st.dataframe([{"Grupa": g, "Σ |starpība| EUR": round(v, 2)} for g, v in sorted(cmp.group_abs_dev.items(), key=lambda kv: -kv[1])],
                     hide_index=True, use_container_width=True)
    if cmp.hours:
        st.markdown("**Stundu plāns/fakts pa posmiem**")
        st.dataframe([{"Posms": h["stage"], "Prognoze h": None if h["forecast_hours"] is None else round(h["forecast_hours"], 2),
                       "Fakts h": h["actual_hours"], "Kontroltāmes plāns h": h["sheet_plan_hours"], "Starpība h": None if h["diff_h"] is None else round(h["diff_h"], 2),
                       "Novirze %": _pct(h["abs_pct"]), "Piezīme": h["note"]} for h in cmp.hours], hide_index=True, use_container_width=True)
    if cmp.uncomparable:
        with st.expander(f"Nav salīdzināmas rindas ({len(cmp.uncomparable)})"):
            for why, name in cmp.uncomparable:
                st.write(f"• {name}: {why}")
    if cmp.unmatched_actual:
        with st.expander(f"Nesasaistītas FAKTA rindas ({len(cmp.unmatched_actual)}): nav prognozē"):
            st.dataframe([{"Artikuls": u["code"], "Nosaukums": u["name"], "Segums": u["scope"], "Vienība": u["unit"], "Fakts daudz.": u["actual_qty"],
                           "Fakts EUR": _eur(u["actual_sum"])} for u in cmp.unmatched_actual], hide_index=True, use_container_width=True)
    if cmp.unmatched_forecast:
        with st.expander(f"Nesasaistītas PROGNOZES rindas ({len(cmp.unmatched_forecast)}): nav faktā"):
            st.dataframe([{"Artikuls": u["code"], "Nosaukums": u["name"], "Segums": u["scope"], "Grupa": u["group"],
                           "Prognoze EUR": _eur(u["forecast_sum"])} for u in cmp.unmatched_forecast], hide_index=True, use_container_width=True)
    for note in cmp.notes:
        st.info(note)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Artikuls", "Nosaukums", "Segums", "Prognoze_daudz", "Fakts_daudz", "Prognoze_EUR", "Fakts_EUR", "Starpiba_EUR", "Novirze_%"])
    for l in cmp.material_lines + cmp.external_lines:
        w.writerow([l["code"], l["name"], l["scope"], l["forecast_qty"], l["actual_qty"], _eur(l["forecast_sum"]), _eur(l["actual_sum"]), _eur(l["diff_eur"]),
                    _pct(l["abs_pct"])])
    st.download_button("Lejupielādēt salīdzinājumu (CSV)", "﻿" + buf.getvalue(), file_name="MLK_prognoze_pret_faktu.csv", mime="text/csv", key=f"bp_cmpcsv_{ver}")

    st.markdown("**Kalibrētā / PD versija (ATSEVIŠĶA kopija; AD projekts un prognoze nemainās)**")
    suggestions = suggest_calibration(cmp)
    picked = [s for s in suggestions if st.checkbox(s["label"], key=f"bp_cal_{ver}_{s['article']}_{s['field']}")]
    d1, d2 = st.columns(2)
    if d1.button("Izveidot kalibrēto versiju (kopija)", key=f"bp_mkcal_{ver}", use_container_width=True):
        st.session_state["bp_derived"] = ("kalibrēta", make_derived_project(project, stage="kalibrēta", label="kalibrēta", snapshot_id=snapshot["id"], suggestions=picked),
                                         len(picked))
    if d2.button("Izveidot PD detalizācijas kopiju", key=f"bp_mkpd_{ver}", use_container_width=True):
        st.session_state["bp_derived"] = ("PD", make_derived_project(project, stage="PD", label="PD detalizācija", snapshot_id=snapshot["id"]), 0)
    derived = st.session_state.get("bp_derived")
    if derived:
        stage, new, n = derived
        st.success(f"Izveidota atsevišķa «{stage}» versija «{new['name']}» (piemērotie priekšlikumi: {n}). AD projekts nav mainīts.")
        st.download_button("Lejupielādēt šo versiju (JSON)", export_project(new), file_name=f"MLK_projekts_{stage}.json", mime="application/json",
                           key=f"bp_dl_derived_{ver}")
