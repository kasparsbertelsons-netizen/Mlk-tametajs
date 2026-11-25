"""Streamlit saskarne AD režīmam (Issue #4).

Plūsma: PDF (nav obligāts) → kandidāti ar avota lapu → lietotājs ievada un
apstiprina katra moduļa L un W → pamatrāmja aprēķins (`src/floor_frame.py`).
Aprēķins netiek veikts, kamēr izmēri nav apstiprināti.
"""
import csv
import io

import streamlit as st

from src.ad_plan import scan_plan_pages
from src.floor_frame import (
    PERIMETER_WIDTH_MM, SCOPE_NOTE, WIDTH_REVIEW_LIMIT_MM, FrameParams,
    calculate_module, export_rows, summarize_modules,
)
from src.pdf_reader import read_pdf

MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_MODULES = 10
MANUAL_SOURCE = "Ievadīts manuāli"


@st.cache_data(show_spinner=False, max_entries=4)
def _scan_pdf(data: bytes) -> dict:
    pdf = read_pdf(data)
    scan = scan_plan_pages([page["text"] for page in pdf["pages"]])
    scan["page_count"] = len(pdf["pages"])
    return scan


def _render_candidates(scan: dict):
    floor_pages, skipped = scan["floor_pages"], scan["skipped_pages"]
    st.caption(
        f"Nolasītas {scan['page_count']} lapas. PDF teksts nepierāda moduļa ģeometriju: "
        "tālāk redzamie skaitļi ir tikai kandidāti, tie nav apstiprināti un nav ranžēti. "
        "L un W jāievada un jāapstiprina pašam.")
    rows = [{"Lapa": page["page"], "Izmērs (mm)": c["value_mm"], "Atkārtojumi": c["count"],
             "Fragments": c["context"]}
            for page in floor_pages for c in page["candidates"]]
    if not floor_pages:
        st.warning("Nav atrasta atpazīstama grīdas plāna lapa. Ievadi L un W manuāli un "
                   "pārbaudi tos pret rasējumu.")
    elif not rows:
        st.warning("Grīdas plāna lapās nav atrasts neviens izmēra kandidāts. Ievadi L un W manuāli.")
    else:
        st.subheader("Izmēru kandidāti no grīdas plāna")
        st.dataframe(rows, hide_index=True, use_container_width=True)
    excluded = [{"Lapa": page["page"], "Iemesls": page["reason"], "Skaitļi": ""} for page in skipped]
    for page in floor_pages:
        if page["excluded_numbers"]:
            values = ", ".join(str(item["value_mm"]) for item in page["excluded_numbers"])
            excluded.append({"Lapa": page["page"], "Iemesls": "Terase: skaitļi izslēgti",
                             "Skaitļi": values})
    if excluded:
        with st.expander("Izslēgtie avoti (jumts, titullapa/saraksts, terases)"):
            st.dataframe(excluded, hide_index=True, use_container_width=True)


def _module_inputs(index: int, sources: list) -> dict:
    with st.container(border=True):
        st.markdown(f"**Modulis {index + 1}**")
        name = st.text_input("Nosaukums", value=f"Modulis {index + 1}", max_chars=60,
                             key=f"ad_name_{index}")
        c1, c2, c3 = st.columns(3)
        length = c1.number_input("Garums L (mm)", min_value=0, max_value=100000, value=0,
                                 step=100, key=f"ad_L_{index}")
        width = c2.number_input("Platums W (mm)", min_value=0, max_value=100000, value=0,
                                step=100, key=f"ad_W_{index}")
        perimeter = c3.number_input(
            f"Perimetra sijas platums (mm); noklusējums {PERIMETER_WIDTH_MM}, nav nolasīts no rasējuma",
            min_value=1, max_value=1000, value=PERIMETER_WIDTH_MM, step=10, key=f"ad_perim_{index}")
        source = st.selectbox("Izmēru avots", sources, key=f"ad_src_{index}")
        nonstandard = False
        if perimeter != PERIMETER_WIDTH_MM:
            nonstandard = st.checkbox(
                f"Apstiprinu nestandarta perimetra platumu {perimeter} mm "
                "(tikai, ja tas ir nepārprotami norādīts rasējumā)", key=f"ad_nonstd_{index}")
        wide = True
        if width > WIDTH_REVIEW_LIMIT_MM:
            wide = st.checkbox(
                f"Platums {width} mm pārsniedz orientējošo {WIDTH_REVIEW_LIMIT_MM} mm; "
                "apstiprinu, ka tas ir pareizs", key=f"ad_wide_{index}")
        confirmed = st.checkbox(
            "Apstiprinu, ka L un W ir šī taisnstūra moduļa ārējie grīdas rāmja izmēri",
            key=f"ad_confirm_{index}")
    return {"name": name.strip() or f"Modulis {index + 1}", "length": length, "width": width,
            "perimeter": perimeter, "source": source, "nonstandard": nonstandard,
            "wide": wide, "confirmed": confirmed}


def _render_module_result(result):
    st.markdown(f"#### {result.name}")
    a, b, c, d = st.columns(4)
    a.metric("Šķērssijas (gab.)", result.cross_count)
    b.metric("Sijas moduļā (gab.)", result.total_pieces)
    c.metric("Kokmateriāli moduļā", f"{result.total_volume_m3:.5f} m³")
    d.metric("Atlikums (mm)", result.remainder_mm)
    st.dataframe([row.to_dict() for row in result.rows], hide_index=True, use_container_width=True)
    for warning in result.warnings:
        st.warning(f"{result.name}: {warning.message}")
    for note in result.notes:
        st.caption(note)
    with st.expander("Šķērssiju novietojums (mm no moduļa gala)"):
        st.write(", ".join(f"{k}.: {s}–{e}" for k, (s, e) in enumerate(result.cross_positions, 1))
                 or "Šķērssiju nav.")


def render_ad_mode():
    st.info("Aprēķins notiek tikai no lietotāja apstiprinātiem moduļu izmēriem. " + SCOPE_NOTE)
    upload = st.file_uploader("Augšupielādē arhitektūras daļas PDF (AD) — nav obligāti",
                              type=["pdf"], key="ad_pdf",
                              help="PDF tiek analizēts šajā sesijā; programma to neievieto GitHub.")
    scan = None
    if upload is not None:
        if upload.size > MAX_PDF_BYTES:
            st.error("Maksimālais PDF izmērs ir 30 MB.")
        else:
            try:
                scan = _scan_pdf(upload.getvalue())
            except (ValueError, RuntimeError) as error:
                st.error(f"PDF neizdevās nolasīt: {error}")
            except Exception as error:  # bojāts PDF u. c.
                st.error(f"PDF analīzes kļūda: {error}")
    if scan:
        _render_candidates(scan)
    sources = [MANUAL_SOURCE] + [f"PDF {page['page']}. lapa"
                                 for page in (scan or {}).get("floor_pages", [])]

    st.subheader("Apstiprināmie moduļi")
    st.caption("Katrs fiziskais modulis ir savs taisnstūris. L/U formas moduļus automātiski "
               "nesadala: ievadi atsevišķus taisnstūrus. Terases neieskaita.")
    count = st.number_input("Moduļu skaits", min_value=1, max_value=MAX_MODULES, value=1,
                            step=1, key="ad_module_count")
    results = []
    for index in range(int(count)):
        data = _module_inputs(index, sources)
        if not data["confirmed"]:
            st.info(f"{data['name']}: gaida apstiprinājumu; aprēķins netiek veikts.")
            continue
        if data["length"] == 0 or data["width"] == 0:
            st.warning(f"{data['name']}: ievadi L un W.")
            continue
        if not data["wide"]:
            st.warning(f"{data['name']}: platums {data['width']} mm virs {WIDTH_REVIEW_LIMIT_MM} mm "
                       "nav apstiprināts; aprēķins netiek veikts.")
            continue
        try:
            results.append(calculate_module(
                data["length"], data["width"], name=data["name"], source=data["source"],
                params=FrameParams(perimeter_width_mm=data["perimeter"]),
                nonstandard_confirmed=data["nonstandard"]))
        except ValueError as error:
            st.error(f"{data['name']}: {error}")

    if not results:
        return
    for result in results:
        _render_module_result(result)

    total = summarize_modules(results)
    st.subheader("Kopsavilkums (tikai pamatrāmis)")
    x, y, z = st.columns(3)
    x.metric("Aprēķinātie moduļi", total["modules"])
    y.metric("Sijas kopā (gab.)", total["pieces"])
    z.metric("Kokmateriāli kopā", f"{total['volume_m3']:.5f} m³")
    st.dataframe([{"Modulis": r.name, "L (mm)": r.length_mm, "W (mm)": r.width_mm,
                   "Sijas (gab.)": r.total_pieces, "m³": r.total_volume_m3,
                   "Atlikums (mm)": r.remainder_mm, "Jāpārbauda": "JĀ" if r.needs_review else "",
                   "Avots": r.source} for r in results], hide_index=True, use_container_width=True)
    if total["needs_review"]:
        st.warning(f"Moduļi ar atzīmi 'jāpārbauda': {total['needs_review']}.")
    st.warning(SCOPE_NOTE)

    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerows(export_rows(results))
    st.download_button("Lejupielādēt pamatrāmja tabulu (CSV Excel)", "﻿" + buffer.getvalue(),
                       file_name="MLK_AD_pamatramis.csv", mime="text/csv")
