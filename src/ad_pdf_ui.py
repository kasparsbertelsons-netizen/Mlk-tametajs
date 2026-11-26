"""Streamlit sadaļa «AD PDF → tāmes ievaddati» (Issue #16): augšupielāde → kandidāti ar lappusi/avotu/pārliecību → apstiprināšana → pārnese.

PDF tiek apstrādāts TIKAI šīs sesijas atmiņā (netiek glabāts projektā, nav kešā, nekas netiek sūtīts). Tāmē tiek pārnesti tikai lietotāja
apstiprinātie kandidāti; nenolasāmie lauki paliek tukši un jāievada manuāli. Reālus rasējumus izmantot tikai lokālajā versijā (127.0.0.1).
"""
import hashlib

import pandas as pd
import streamlit as st

from src.ad_building import HIGH, KIND_LABELS, LOW, MEDIUM, apply_candidates, scan_ad_building
from src.ad_vector import render_preview_png
from src.project_io import LOCAL_DATA_REMINDER

SAFE_KEY = "bp_ad_safe"
SCAN_KEY = "bp_ad_scan"                      # sesijā: (pdf kontrolsumma, BuildingScan, pdf baiti priekšskatījumam); dzēšams


def render_ad_import(project, ver, key_project, key_ver):
    st.caption("AD arhitektūras PDF ir sākotnējā piedāvājuma vienīgais projektēšanas dokuments. Programma atrod KANDIDĀTUS (moduļi, telpas, sienu posmi, "
               "zelmiņi, atveres, jumta slīpnes, konstrukciju tipi un slāņi) ar lappusi, avotu un pārliecību; tāmē nonāk tikai tas, ko APSTIPRINI. "
               "Nenolasīts lauks paliek tukšs (nav nulle) un jāievada manuāli. Ārējā fasādes kontūra netiek sajaukta ar pamatrāmi. Notācija: "
               "`docs/AD_BUILDING_IMPORT.md`.")
    st.warning(LOCAL_DATA_REMINDER)
    upload = st.file_uploader("AD arhitektūras PDF (sintētisks paraugs: samples/ad_building/)", type=["pdf"], key="bp_adpdf")                   # fiksēta atslēga: PDF paliek pēc pārnešanas
    if upload is None:
        st.session_state.pop(SCAN_KEY, None)                # PDF noņemts → sesijas dati dzēsti
        st.session_state.pop(SAFE_KEY, None)
        _provenance(project)
        return
    data = upload.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    cached = st.session_state.get(SCAN_KEY)
    if cached is None or cached[0] != digest:
        try:
            scan = scan_ad_building(data)
        except (ValueError, RuntimeError) as error:
            st.error(f"PDF neizdevās nolasīt: {error}")
            st.session_state.pop(SCAN_KEY, None)
            return
        st.session_state[SCAN_KEY] = (digest, scan, data)
    _digest, scan, pdf_bytes = st.session_state[SCAN_KEY]
    st.write(f"Lapas: {len(scan.pages)}; kandidāti: **{len(scan.candidates)}**. " + ", ".join(f"lpp. {p['page']} — {p['kind']}" for p in scan.pages))
    for note in scan.notes:
        st.info(note)
    if not scan.candidates:
        return
    st.markdown("**Kandidāti** (atzīmē, ko apstiprini; «jāpārbauda» rindas pārbaudi pirms apstiprināšanas)")
    if st.button("Atzīmēt visus droši nolasāmos (pārliecība ≥ vidēja, bez problēmām)", key=f"bp_adsafe_{ver}"):
        st.session_state[SAFE_KEY] = digest                  # izvēle paliek spēkā šim PDF (arī pēc nākamās darbības, piem., «Pārnest»)
    safe = st.session_state.get(SAFE_KEY) == digest
    rows = []
    for c in scan.candidates:
        default = c.confidence in (HIGH, MEDIUM) and not c.issues
        rows.append({"Apstiprināt": default if safe else False, "ID": c.id, "Lauks": KIND_LABELS.get(c.kind, c.kind), "Apraksts": c.label,
                     "Lpp.": c.page, "Avots": c.source, "Pārliecība": c.confidence, "Statuss": c.status,
                     "Problēmas": "; ".join(c.issues), "Piezīmes": "; ".join(c.notes), "Pierādījums": c.evidence})
    edited = st.data_editor(pd.DataFrame(rows), hide_index=True, use_container_width=True, key=f"bp_adcand_{ver}_{'s' if safe else 'n'}",
                            disabled=[c for c in rows[0] if c != "Apstiprināt"],
                            column_config={"Apstiprināt": st.column_config.CheckboxColumn("Apstiprināt")})
    accepted = [r["ID"] for r in edited.to_dict("records") if r["Apstiprināt"]]
    low = [c.id for c in scan.candidates if c.id in accepted and (c.confidence == LOW or c.issues)]
    if low:
        st.warning("Apstiprināti kandidāti ar zemu pārliecību vai problēmām: " + ", ".join(low) + ". Nepilni dati netiks pārnesti (skat. rezultātu).")
    c1, c2, c3 = st.columns(3)
    mode = c1.radio("Pārnese", ["Pievienot (dublikāti netiek pievienoti)", "Aizvietot atbilstošās kategorijas"], key=f"bp_admode_{ver}")
    ceiling = c2.checkbox("Griestu platība = neto grīdas platība (pieņēmums)", value=True, key=f"bp_adceil_{ver}")
    types = c3.checkbox("Izmantot konstrukciju tipu receptes (ārsienām/iekšsienām/jumtam)", value=True, key=f"bp_adtypes_{ver}",
                        help="Tad globālie slāņi šīm grupām netiek skaitīti (nav dubultošanas).")
    if st.button("Pārnest apstiprinātos uz tāmi", key=f"bp_adapply_{ver}", disabled=not accepted):
        report = apply_candidates(project, scan, accepted, mode="add" if mode.startswith("Pievienot") else "replace", ceiling_as_floor=ceiling,
                                  use_type_recipes=types)
        st.session_state["bp_notice"] = (f"Pārnesti {len(report.applied)} kandidāti. Izlaisti {len(report.skipped)}: "
                                         + "; ".join(f"{i} ({why})" for i, why in report.skipped[:12])
                                         + ((" | PĀRBAUDI: " + " ".join(report.notes)) if report.notes else ""))
        st.session_state[key_project] = project
        st.session_state[key_ver] = st.session_state.get(key_ver, 0) + 1     # visi ievades lauki tiek atjaunoti no projekta (nevis no vecā widget stāvokļa)
        st.rerun()
    floor_pages = [p["page"] for p in scan.pages if p["kind"] == "floor"]
    if floor_pages and scan.vector.get("pages"):
        with st.expander("Grīdas plāna priekšskatījums (vektoru kontūras)"):
            try:
                st.image(render_preview_png(pdf_bytes, {"pages": scan.vector["pages"]}), use_container_width=True)
            except Exception as error:                      # priekšskatījums nav kritisks
                st.info(f"Priekšskatījums nav pieejams: {error}")
    _provenance(project)


def _provenance(project):
    ad = project.get("ad_import")
    if ad and ad.get("fields"):
        with st.expander(f"Pārnesto lauku izcelsme ({len(ad['fields'])})"):
            st.dataframe([{"Kandidāts": f["candidate"], "Lauks": f["field"], "Lpp.": f["page"], "Avots": f["source"], "Pārliecība": f["confidence"],
                           "Apstiprināts": "jā" if f["confirmed_by_user"] else "nē", "Piezīme": f["note"], "Pierādījums": f["evidence"]}
                          for f in ad["fields"]], hide_index=True, use_container_width=True)
