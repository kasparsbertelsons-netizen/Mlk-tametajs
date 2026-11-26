"""Streamlit sadaļa «Prognozes versijas un faktiskā kontrole» (Issue #16): AD prognozes fiksēšana, lokāla kontroltāmes importēšana, salīdzināšana,
kalibrētā/PD versija kā ATSEVIŠĶA kopija. Faktiskie dati neaizpilda un nepārraksta AD prognozi."""
import csv
import datetime
import io

import streamlit as st

from src.control_import import (
    MONEO_LAYOUT, MONEO_LAYOUT_LABELS, SCOPE_MATERIAL, detect_layout, parse_control_sheet, parse_hours_report, parse_moneo_report,
)
from src.forecast_compare import (
    STAGES, add_version, compare_hours_by_operation, compare_to_actual, freeze_forecast, get_version, make_derived_project, suggest_calibration,
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
    upload = st.file_uploader("Moneo budžeta/faktiskā pārskats vai kontroltāme (.xlsx vai .csv)", type=["xlsx", "csv"], key=f"bp_ctrl_{ver}")
    sheet = None
    if upload is None:
        st.session_state.pop(SHEET_KEY, None)
    else:
        data = upload.getvalue()
        formats = ["Automātiski", "Moneo pārskats (kolonnu burti)", "Vispārīgā kontroltāme (kolonnu virsraksti)"]
        fmt = st.radio("Faila struktūra", formats, horizontal=False, key=f"bp_ctrlfmt_{ver}")
        kind = detect_layout(upload.name, data) if fmt == formats[0] else ("moneo" if fmt == formats[1] else "generic")
        if fmt == formats[0]:
            st.caption(f"Atpazīta struktūra: **{'Moneo pārskats' if kind == 'moneo' else 'vispārīgā kontroltāme'}**.")
        layout = {}
        if kind == "moneo":
            with st.expander("Kolonnu kartējums (maini, ja struktūra atšķiras)"):
                st.caption("Gaidītais izkārtojums: artikulu rindas E=kods, H=apraksts, I/K/N=budžeta daudzums/cena/summa, Q/T/V=faktiskais daudzums/cena/summa; grupas D/G ar O/X; "
                           "posma kontrolsumma F=<bez koda>, P/Z; atkārtota kopsumma J=Kopā. Mērvienību nav (netiek izdomāta).")
                cols = st.columns(3)
                for i, (fld, default) in enumerate(MONEO_LAYOUT.items()):
                    layout[fld] = cols[i % 3].text_input(MONEO_LAYOUT_LABELS[fld], value=default, max_chars=3, key=f"bp_lay_{fld}_{ver}").strip().upper() or default
        sheet = parse_moneo_report(upload.name, data, layout) if kind == "moneo" else parse_control_sheet(upload.name, data)
        for row_no, message in sheet.errors:
            st.error((f"Rinda {row_no}: " if row_no else "") + message)
        for row_no, message in sheet.warnings[:20]:
            st.warning((f"Rinda {row_no}: " if row_no else "") + message)
        if sheet.fatal:
            sheet = None
        else:
            st.write(f"Nolasīts: artikulu rindas **{len(sheet.items)}**, stundu rindas **{len(sheet.hours)}**, kopsummu rindas {len(sheet.totals)} "
                     "(kopsummas netiek summētas — tikai saskaņošanai)." + (f" Projekta virsraksts: {sheet.project_heading}." if sheet.project_heading else ""))
            if sheet.kind == "moneo":
                with st.expander("Importa priekšskatījums (pirmās 60 rindas)"):
                    st.dataframe([{"Rinda": l.row_no, "Tips": l.row_type, "Posms": l.stage, "Grupa": l.group, "Kods": l.code, "Apraksts": l.name,
                                   "Budžeta summa": l.plan_sum, "Faktiskā summa": l.actual_sum} for l in sheet.lines[:60]], hide_index=True, use_container_width=True)
            if sheet.reconciliation:
                st.dataframe([{"Rinda": r["row_no"], "Kopsumma": r["label"], "Veids": r["type"], "Plāns (kopsumma)": r["total_plan"], "Plāns (Σ artikuli)": r["sum_plan"],
                               "Fakts (kopsumma)": r["total_actual"], "Fakts (Σ artikuli)": r["sum_actual"], "Saskan": "✓" if r["ok"] else "✗"}
                              for r in sheet.reconciliation], hide_index=True, use_container_width=True)
    versions_ok = bool(versions)
    snapshot = None
    if versions_ok:
        choice = st.selectbox("Salīdzināmā prognozes versija", [f"{v['id']} — {v['label']}" for v in versions], key=f"bp_vsel_{ver}")
        snapshot = get_version(project, choice.split(" — ")[0])
    if snapshot is not None:
        _render_hours_report(snapshot, ver)
    if sheet is None or snapshot is None:
        return
    if sheet.kind == "moneo":
        st.info("Moneo pārskatā izmaksu segums nav norādīts: pēc noklusējuma rindas tiek uzskatītas par MATERIĀLIEM (tava izvēle zemāk; ārpakalpojumu rindas nesakritīs "
                "ar prognozes «ārējām izmaksām»).")
    scope_choice = st.selectbox("Rindām bez norādīta izmaksu seguma", ["Nesalīdzināt (nav norādīts)", "Uzskatīt par materiāliem (mana izvēle)"],
                                index=1 if sheet.kind == "moneo" else 0, key=f"bp_dscope_{ver}_{sheet.kind}")
    cmp = compare_to_actual(snapshot, sheet, default_scope=SCOPE_MATERIAL if scope_choice.startswith("Uzskatīt") else None)
    t = cmp.totals
    st.markdown("**Sasaistīto rindu starpības** (tikai rindas, kas saistītas pēc artikula un izmaksu seguma — NAV visas ēkas precizitāte)")
    m1, m2, m3 = st.columns(3)
    m1.metric("Materiāli (sasaistītie): starpība (fakts − prognoze)", f"{t['materials_diff']:.2f} EUR", delta=None if t["materials_abs_pct"] is None else f"{t['materials_abs_pct']:.2f} % (abs.)")
    m2.metric("Ārējās izmaksas (sasaistītās): starpība", f"{t['external_diff']:.2f} EUR", delta=None if t["external_abs_pct"] is None else f"{t['external_abs_pct']:.2f} % (abs.)")
    m3.metric("Stundas (sasaistītie posmi): starpība", f"{t['hours_diff']:.2f} h", delta=None if t["hours_abs_pct"] is None else f"{t['hours_abs_pct']:.2f} % (abs.)")
    st.caption(f"Absolūto EUR noviržu summa (sasaistītās rindas): {t['abs_dev_total']:.2f} EUR. Starpība = fakts − prognoze; novirze % = |prognoze − fakts| / |fakts|. "
               "Faktiskās rindas no vairākiem posmiem tiek AGREGĒTAS pa artikulu (prognoze netiek dubultota).")
    if cmp.scope_totals:
        st.markdown("**Visa saskaņotā tvēruma kopsummas** (ar nesasaistītajām rindām) un pārklājums")
        st.dataframe([{"Izmaksu segums": sc, "Prognoze kopā EUR": _eur(v["forecast_total"]), "Fakts kopā EUR": _eur(v["actual_total"]),
                       "Starpība kopā EUR": _eur(v["diff_total"]), "Novirze % (pret faktu)": _pct(v["abs_pct_total"]),
                       "Sasaistīts fakts EUR": _eur(v["matched_actual"]), "Nesasaistīts fakts EUR": _eur(v["unmatched_actual"]),
                       "Nesasaistīta prognoze EUR": _eur(v["unmatched_forecast"]), "Fakta pārklājums %": _pct(v["coverage_actual_pct"]),
                       "Prognozes rindas bez cenas": v["forecast_unpriced_rows"]} for sc, v in cmp.scope_totals.items()],
                     hide_index=True, use_container_width=True)
        if t["uncomparable_actual_sum"]:
            st.warning(f"Nav salīdzināms (izmaksu segums nav norādīts/atšķiras): {t['uncomparable_actual_sum']:.2f} EUR fakta. Tas NAV iekļauts nevienā tvērumā.")
        low = [sc for sc, v in cmp.scope_totals.items() if v["coverage_actual_pct"] is not None and v["coverage_actual_pct"] < 95]
        if low:
            st.info("Sasaistīto rindu novirze neraksturo visu tvērumu «" + "», «".join(low) + "»: faktiskā pārklājuma < 95 %. Skatiet nesasaistītās rindas.")
    for title, lines in (("Materiāli (saistītās rindas)", cmp.material_lines), ("Ārējās izmaksas (saistītās rindas)", cmp.external_lines)):
        if lines:
            st.markdown(f"**{title}**")
            st.dataframe([{"Artikuls": l["code"], "Nosaukums": l["name"], "Grupa": l["group"], "Vienība (prog./fakts)": f"{l['forecast_unit']} / {l['actual_unit']}",
                           "Prognoze daudz.": None if l["forecast_qty"] is None else round(l["forecast_qty"], 3), "Fakts daudz.": l["actual_qty"],
                           "Prognoze EUR": _eur(l["forecast_sum"]), "Fakts EUR": _eur(l["actual_sum"]), "Starpība EUR": _eur(l["diff_eur"]),
                           "Novirze %": _pct(l["abs_pct"]), "Faktiskās rindas": len(l["sources"]), "Piezīmes": "; ".join(l["issues"])} for l in lines], hide_index=True, use_container_width=True)
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


def _render_hours_report(snapshot, ver):
    """Stundu pārskats (Darbība / Stundas: Reāli, Plānots): salīdzina pa OPERĀCIJĀM ar fiksētās prognozes darba operācijām; atšķirīgus nosaukumus kartē lietotājs."""
    with st.expander("Stundu pārskats (Darbība; Stundas: Reāli, Plānots)"):
        st.caption("Divu rindu virsraksts: A=Darbība, B=Stundas; nākamajā rindā B=Reāli, C=Plānots. Turpmāk A=operācija, B=faktiskās, C=plānotās; «Kopā:» ir kontrolsumma, nevis operācija.")
        up = st.file_uploader("Stundu pārskats (.xlsx vai .csv)", type=["xlsx", "csv"], key=f"bp_hours_{ver}")
        if up is None:
            return
        layout = {}
        with st.expander("Kolonnu kartējums (ja struktūra atšķiras)"):
            c = st.columns(3)
            for i, (fld, default, label) in enumerate((("name", "A", "Darbība"), ("actual", "B", "Reāli"), ("plan", "C", "Plānots"))):
                layout[fld] = c[i].text_input(label, value=default, max_chars=3, key=f"bp_hl_{fld}_{ver}").strip().upper() or default
        rep = parse_hours_report(up.name, up.getvalue(), layout)
        for row_no, message in rep.errors:
            st.error((f"Rinda {row_no}: " if row_no else "") + message)
        for row_no, message in rep.warnings[:15]:
            st.warning((f"Rinda {row_no}: " if row_no else "") + message)
        if rep.fatal:
            return
        forecast_names = sorted({x["name"] for x in snapshot["labour"]})
        known = {n.lower() for n in forecast_names}
        mapping = {}
        unknown = sorted({o.name for o in rep.operations if o.name.lower() not in known})
        if unknown:
            st.caption("Operācijas, kuras nav prognozē pēc nosaukuma: izvēlies atbilstību (vai atstāj «— nav —»).")
            for name in unknown:
                pick = st.selectbox(name, ["— nav —"] + forecast_names, key=f"bp_hmap_{ver}_{name}")
                if pick != "— nav —":
                    mapping[name] = pick
        cmp = compare_hours_by_operation(snapshot, rep, mapping)
        t = cmp.totals
        st.dataframe([{"Operācija": l["name"], "Prognoze h": round(l["forecast_hours"], 2), "Fakts h": l["actual_hours"], "Kontroltāmes plāns h": l["sheet_plan_hours"],
                       "Starpība h": None if l["diff_h"] is None else round(l["diff_h"], 2), "Novirze %": _pct(l["abs_pct"]), "Faktiskās rindas": len(l["sources"]),
                       "Piezīmes": "; ".join(l["issues"])} for l in cmp.lines], hide_index=True, use_container_width=True)
        st.write(f"Sasaistītās operācijas: prognoze **{t['matched_forecast']:.2f} h**, fakts **{t['matched_actual']:.2f} h**, starpība {t['matched_diff']:.2f} h "
                 f"({'—' if t['matched_abs_pct'] is None else f'{t['matched_abs_pct']:.2f} %'} abs.). **Visa tvēruma** kopsummas: prognoze {t['all_forecast']:.2f} h, "
                 f"fakts {t['all_actual']:.2f} h, starpība {t['all_diff']:.2f} h; nesasaistīts fakts {t['unmatched_actual_hours']:.2f} h, nesasaistīta prognoze "
                 f"{t['unmatched_forecast_hours']:.2f} h.")
        if cmp.unmatched_actual:
            st.info("Nesasaistītas FAKTA operācijas: " + "; ".join(f"{u['name']} ({u['actual']} h)" for u in cmp.unmatched_actual))
        if cmp.unmatched_forecast:
            st.info("Nesasaistītas PROGNOZES operācijas: " + "; ".join(f"{u['name']} ({u['forecast_hours']:.2f} h)" for u in cmp.unmatched_forecast))
