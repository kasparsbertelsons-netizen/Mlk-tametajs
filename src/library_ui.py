"""Streamlit sadaļa «Bibliotēka» (Issue #20): lokāls imports → priekšskatījums → piemērošana; AD komplektu izvēle.

Fails tiek lasīts TIKAI atmiņā (netiek sūtīts un netiek saglabāts uz servera). Reālus uzņēmuma datus izmantot tikai lokālajā versijā (127.0.0.1).
"""
import copy
import pathlib

import pandas as pd
import streamlit as st

from src.library import (
    ST_APPROVED, ST_HISTORICAL, ST_UNAPPROVED, apply_kits, apply_library, export_library, kit_selection, kit_total, library_fingerprint,
    library_summary, parse_library, preview_library,
)
from src.project_io import LOCAL_DATA_REMINDER

LIB_KEY = "bp_library"                          # sesijā: ielādētā bibliotēka (dict) vai None
SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "samples" / "library" / "biblioteka_sintetiska.json"
KEEP = "(kā komplektam)"


def _bump(key_ver):
    st.session_state[key_ver] = st.session_state.get(key_ver, 0) + 1


def _report_tables(rep):
    st.write(f"Jaunas: **{len(rep.added)}** · atjaunotas: **{len(rep.updated)}** · nemainītas: **{len(rep.unchanged)}** · izlaistas: **{len(rep.skipped)}**")
    if rep.skipped:
        st.dataframe(pd.DataFrame([{"Kods": c, "Ieraksts": n, "Iemesls": w} for c, n, w in rep.skipped]), hide_index=True, use_container_width=True)
    if rep.prices_not_applied:
        st.dataframe(pd.DataFrame([{"Artikuls": a, "Cena nav piemērota": w} for a, w in rep.prices_not_applied]), hide_index=True, use_container_width=True)
    for w in rep.warnings:
        st.warning(w)


def render_library(project, key_project, key_ver):
    ver = st.session_state.get(key_ver, 0)
    st.caption("Atsevišķs lokāls bibliotēkas fails (JSON): katalogs ar cenu derīgumu, receptes (ģeometriskas formulas / vēsturiski koeficienti), "
               "normstundas pēc operācijas un pamata, AD komplekti ar līmeņiem. Bibliotēka NAV projekts un NAV faktiskā kontroltāme. "
               "Dokumentācija: `docs/LIBRARY.md`. Option List nav obligāts.")
    st.warning(LOCAL_DATA_REMINDER)
    c1, c2 = st.columns(2)
    if c2.button("Ielādēt sintētisko bibliotēku (DEMO)", key="bp_lib_demo", use_container_width=True):
        result = parse_library(SAMPLE_PATH.read_bytes())
        st.session_state[LIB_KEY] = result.library
        st.session_state["bp_lib_msgs"] = (result.errors, result.warnings)
    upload = c1.file_uploader("Bibliotēkas fails (.json)", type=["json"], key=f"bp_lib_up")
    if upload is not None:
        digest = hash(upload.getvalue())
        if st.session_state.get("bp_lib_digest") != digest:
            result = parse_library(upload.getvalue())
            st.session_state["bp_lib_digest"] = digest
            st.session_state[LIB_KEY] = result.library
            st.session_state["bp_lib_msgs"] = (result.errors, result.warnings)
    errors, warnings = st.session_state.get("bp_lib_msgs", ([], []))
    for e in errors:
        st.error(e)
    with st.expander(f"Brīdinājumi importā ({len(warnings)})", expanded=False) if warnings else st.container():
        for w in warnings:
            st.warning(w)
    lib = st.session_state.get(LIB_KEY)
    if not lib:
        st.info("**Statuss:** bibliotēka nav ielādēta. **Nākamā darbība:** augšupielādē bibliotēkas JSON vai ielādē sintētisko DEMO bibliotēku.")
        return
    counts, by_status = library_summary(lib)
    st.success(f"Bibliotēka «{lib['meta']['name']}» v{lib['meta']['version']} (kontrolsumma {library_fingerprint(lib)}): "
               + ", ".join(f"{k} {v}" for k, v in counts.items()) + ". Statusi: " + ", ".join(f"{k} {v}" for k, v in by_status.items()) + ".")
    include_hist = st.checkbox("Piemērot arī VĒSTURISKOS koeficientus (paliek neapstiprināti, ar atzīmi «nav validēts»)", value=False, key=f"bp_lib_hist_{ver}")
    st.markdown("**Priekšskatījums** (projekts vēl nav mainīts)")
    preview = preview_library(project, lib, include_historical=include_hist)
    _report_tables(preview)
    if st.button("Piemērot bibliotēku projektam", key=f"bp_lib_apply_{ver}", type="primary"):
        report = apply_library(project, lib, include_historical=include_hist)
        st.session_state[key_project] = project
        _bump(key_ver)
        st.session_state["bp_notice"] = (f"Bibliotēka piemērota: jaunas {len(report.added)}, atjaunotas {len(report.updated)}, nemainītas {len(report.unchanged)}, "
                                         f"izlaistas {len(report.skipped)}. Atkārtota piemērošana ierakstus nedublē.")
        st.rerun()
    st.download_button("Lejupielādēt bibliotēku (JSON)", export_library(lib), file_name="biblioteka.json", mime="application/json", key=f"bp_lib_dl_{ver}")
    if lib["kits"] and (project.get("lib") or {}).get("name"):
        _render_kits(project, lib, key_project, key_ver, ver)
    elif lib["kits"]:
        st.info("Komplektu izvēle parādīsies pēc bibliotēkas piemērošanas projektam.")


def _render_kits(project, lib, key_project, key_ver, ver):
    st.markdown("### AD komplektācija (standarta noklusējums + klienta izvēles)")
    st.caption("Katram komplektam ir viens aktīvs līmenis; standarta un izvēlētais aprīkojums netiek skaitīti abi. Pozīciju var aizstāt (cits līmenis), "
               "izslēgt vai papildināt. Konkrēts modelis un artikuls tiek precizēts PD/iepirkuma stadijā. Option List nav obligāts.")
    stored = copy.deepcopy((project.get("lib") or {}).get("kits") or {})
    choices = {}
    for kit in lib["kits"]:
        sel = kit_selection(project, kit["code"])
        with st.container(border=True):
            st.markdown(f"**{kit['name']}** — {kit['group']}")
            enabled = st.checkbox("Iekļaut komplektu", value=sel["enabled"], key=f"bp_kit_en_{kit['code']}_{ver}")
            level = st.selectbox("Līmenis", kit["levels"], index=kit["levels"].index(sel["level"] if sel["level"] in kit["levels"] else kit["default_level"]),
                                 key=f"bp_kit_lvl_{kit['code']}_{ver}")
            pos_levels, skip = {}, []
            for pos in kit["positions"]:
                cols = st.columns([3, 2, 1])
                cols[0].write(pos["name"])
                pl = cols[1].selectbox("Pozīcijas līmenis", [KEEP] + kit["levels"], index=([KEEP] + kit["levels"]).index(sel["pos_levels"].get(pos["code"], KEEP))
                                       if sel["pos_levels"].get(pos["code"], KEEP) in kit["levels"] + [KEEP] else 0,
                                       key=f"bp_kit_pl_{kit['code']}_{pos['code']}_{ver}", label_visibility="collapsed")
                if pl != KEEP:
                    pos_levels[pos["code"]] = pl
                if cols[2].checkbox("Izslēgt", value=pos["code"] in sel["skip"], key=f"bp_kit_sk_{kit['code']}_{pos['code']}_{ver}"):
                    skip.append(pos["code"])
            adds = pd.DataFrame(sel["add"], columns=["name", "unit", "qty", "article"])
            for col in ("name", "unit", "article"):
                adds[col] = adds[col].astype(object)
            adds["qty"] = pd.to_numeric(adds["qty"], errors="coerce")
            edited = st.data_editor(adds, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"bp_kit_add_{kit['code']}_{ver}",
                                    column_config={"name": st.column_config.TextColumn("Papildu pozīcija"), "unit": st.column_config.TextColumn("Vienība"),
                                                   "qty": st.column_config.NumberColumn("Daudzums", min_value=0.0), "article": st.column_config.TextColumn("Artikuls")})
            add = [{k: (None if pd.isna(v) else v) for k, v in rec.items()} for rec in edited.to_dict("records") if any(not pd.isna(v) and v not in ("", None) for v in rec.values())]
            choice = {"enabled": enabled, "level": level, "pos_levels": pos_levels, "skip": skip, "add": add}
            if choice != {"enabled": True, "level": kit["default_level"], "pos_levels": {}, "skip": [], "add": []}:
                choices[kit["code"]] = choice
            totals = []
            for lv in kit["levels"]:
                tmp = copy.deepcopy(project)
                tmp.setdefault("lib", {}).setdefault("kits", {})[kit["code"]] = {**choice, "level": lv, "enabled": True}
                value = kit_total(tmp, lib, kit["code"])
                totals.append(f"{lv}: " + ("cena nav pilna" if value is None else f"{value:,.2f} EUR".replace(",", " ")))
            st.caption("Komplekta cena pa līmeņiem (bez PVN; ar pārējo izvēli): " + " · ".join(totals))
    if choices != stored:
        project["lib"]["kits"] = choices
        report = apply_kits(project, lib)
        st.session_state[key_project] = project
        _bump(key_ver)
        st.session_state["bp_notice"] = "Komplektācija atjaunināta; tāme pārrēķināta (fiksētās prognozes versijas nav mainītas)." + (
            " Izlaisti: " + "; ".join(f"{c} ({w})" for c, _n, w in report.skipped[:6]) if report.skipped else "")
        st.rerun()
