"""Streamlit saskarne AD režīmam (Issue #4).

Plūsma: PDF (nav obligāts) → pagaidu kandidāti ar avota lapu → lietotājs ievada
katra moduļa L un W un spiež "Apstiprināt" → pamatrāmja aprēķins
(`src/floor_frame.py`).

Apstiprinājums ir piesaistīts konkrētai ievades versijai (L, W, perimetrs,
avots, PDF identitāte, nestandarta/platuma apstiprinājumi). Mainoties jebkuram no
tiem, apstiprinājums vairs neder. PDF teksts netiek glabāts globālā kešā: tikai
šīs sesijas `st.session_state`, un tas tiek dzēsts, mainot vai noņemot PDF.
"""
import csv
import hashlib
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
SCAN_KEY = "ad_scan"                   # sesijas ietvaros; dzēšams
CONFIRMATIONS_KEY = "ad_confirmations"  # {moduļa indekss: ievades pirkstu nospiedums}


def _load_scan(upload):
    """(scan, pdf_id, kļūda). Rezultāts glabājas tikai sesijā un tiek dzēsts, mainot/noņemot PDF.

    pdf_id ir pilns SHA-256 no faila satura jebkuram augšupielādētam failam, arī nederīgam vai
    par lielu: identitāte nekad nav tikai nosaukums + izmērs.
    """
    state = st.session_state
    if upload is None:
        state.pop(SCAN_KEY, None)
        return None, None, None
    cached = state.get(SCAN_KEY)
    if cached and cached["file_id"] == upload.file_id:
        return cached["scan"], cached["pdf_id"], cached["error"]
    state.pop(SCAN_KEY, None)
    data = upload.getvalue()
    pdf_id = hashlib.sha256(data).hexdigest()
    scan, error = None, None
    if upload.size > MAX_PDF_BYTES:
        error = "Maksimālais PDF izmērs ir 30 MB."
    else:
        try:
            pdf = read_pdf(data)
            scan = scan_plan_pages([page["text"] for page in pdf["pages"]])
            scan["page_count"] = len(pdf["pages"])
        except (ValueError, RuntimeError) as exc:
            error = f"PDF neizdevās nolasīt: {exc}"
        except Exception as exc:  # bojāts PDF u. c.
            error = f"PDF analīzes kļūda: {exc}"
    state[SCAN_KEY] = {"file_id": upload.file_id, "pdf_id": pdf_id, "scan": scan, "error": error}
    return scan, pdf_id, error


def _render_candidates(scan: dict):
    floor_pages, skipped = scan["floor_pages"], scan["skipped_pages"]
    st.caption(
        f"Nolasītas {scan['page_count']} lapas. Tas ir **pagaidu kandidātu saraksts** no PDF teksta "
        "(heiristika), nevis automātiski noteikta ģeometrija. Teksta PDF nepierāda moduļa "
        "izmērus: kandidāti nav apstiprināti un nav ranžēti. L un W jāievada un jāapstiprina pašam.")
    rows = [{"Lapa": page["page"], "Izmērs (mm)": c["value_mm"], "Atkārtojumi": c["count"],
             "Fragments": c["context"]}
            for page in floor_pages for c in page["candidates"]]
    if not floor_pages:
        st.warning("Nav atrasta atpazīstama grīdas plāna lapa. Ievadi L un W manuāli un "
                   "pārbaudi tos pret rasējumu.")
    elif not rows:
        st.warning("Grīdas plāna lapās nav atrasts neviens izmēra kandidāts. Ievadi L un W manuāli.")
    else:
        st.subheader("Izmēru kandidāti no grīdas plāna (pagaidu)")
        st.dataframe(rows, hide_index=True, use_container_width=True)
    excluded = [{"Lapa": page["page"], "Iemesls": page["reason"], "Skaitļi": ""} for page in skipped]
    for page in floor_pages:
        if page["excluded_numbers"]:
            values = ", ".join(str(item["value_mm"]) for item in page["excluded_numbers"])
            excluded.append({"Lapa": page["page"],
                             "Iemesls": "Rinda ar atslēgvārdu 'terase': skaitļi izslēgti",
                             "Skaitļi": values})
    if excluded:
        with st.expander("Izslēgtie avoti (jumta plāns, titullapa/saraksts, rindas ar 'terase')"):
            st.dataframe(excluded, hide_index=True, use_container_width=True)
    st.caption("Terases tiek izslēgtas tikai pēc atslēgvārda tajā pašā teksta rindā: tas negarantē, "
               "ka visas terases ir izslēgtas. Pārbaudi, vai L un W neietver terasi.")


def _module_inputs(index: int, sources: list, pdf_id) -> dict:
    confirmations = st.session_state.setdefault(CONFIRMATIONS_KEY, {})
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
        # Atslēga satur vērtību: mainoties perimetram/platumam, apstiprinājums sākas no jauna (neatzīmēts).
        nonstandard = False
        if perimeter != PERIMETER_WIDTH_MM:
            nonstandard = st.checkbox(
                f"Apstiprinu nestandarta perimetra platumu {perimeter} mm "
                "(tikai, ja tas ir nepārprotami norādīts rasējumā)",
                key=f"ad_nonstd_{index}_{perimeter}")
        wide = True
        if width > WIDTH_REVIEW_LIMIT_MM:
            wide = st.checkbox(
                f"Platums {width} mm pārsniedz orientējošo {WIDTH_REVIEW_LIMIT_MM} mm; "
                "apstiprinu, ka tas ir pareizs", key=f"ad_wide_{index}_{width}")
        fingerprint = (int(length), int(width), int(perimeter), source, pdf_id, nonstandard, wide)

        if st.button("Apstiprināt šo ievadi (L, W, perimetrs, avots)", key=f"ad_confirm_{index}"):
            if length == 0 or width == 0:
                st.warning("Ievadi L un W, pirms apstiprini.")
            elif perimeter != PERIMETER_WIDTH_MM and not nonstandard:
                st.error("Vispirms atzīmē nestandarta perimetra apstiprinājumu.")
            elif width > WIDTH_REVIEW_LIMIT_MM and not wide:
                st.error(f"Vispirms atzīmē platuma virs {WIDTH_REVIEW_LIMIT_MM} mm apstiprinājumu.")
            else:
                confirmations[index] = fingerprint
        stored = confirmations.get(index)
        confirmed = stored is not None and stored == fingerprint
        if confirmed:
            st.success(f"Apstiprināts: L = {length} mm, W = {width} mm, perimetrs = {perimeter} mm, "
                       f"avots: {source}.")
        elif stored is not None:
            # Neatbilstošais nospiedums tiek dzēsts: atgriežoties pie sākotnējiem datiem (A → B → A)
            # apstiprinājums neatjaunojas pats, vajadzīga jauna apstiprināšana.
            del confirmations[index]
            st.warning("Ievade mainīta pēc apstiprinājuma (L, W, perimetrs, avots vai PDF): "
                       "apstiprinājums atcelts. Apstiprini vēlreiz.")
        else:
            st.info("Gaida apstiprinājumu: aprēķins netiek veikts.")
    return {"name": name.strip() or f"Modulis {index + 1}", "length": int(length),
            "width": int(width), "perimeter": int(perimeter), "source": source,
            "nonstandard": nonstandard, "confirmed": confirmed}


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
    upload = st.file_uploader(
        "Augšupielādē arhitektūras daļas PDF (AD) — nav obligāti", type=["pdf"], key="ad_pdf",
        help="PDF teksts tiek apstrādāts tikai šajā sesijā un netiek ielikts GitHub. Publiski "
             "pieejamā Streamlit lietotnē nav individuālas autentifikācijas: konfidenciālus "
             "rasējumus augšupielādē tikai pēc piekļuves pārbaudes (skat. docs/DEPLOY.md).")
    scan, pdf_id, load_error = _load_scan(upload)
    if load_error:
        st.error(load_error)
    if scan:
        _render_candidates(scan)
    sources = [MANUAL_SOURCE] + [f"PDF {page['page']}. lapa"
                                 for page in (scan or {}).get("floor_pages", [])]

    st.subheader("Apstiprināmie moduļi")
    st.caption("Katrs fiziskais modulis ir savs taisnstūris. L/U formas moduļus automātiski "
               "nesadala: ievadi atsevišķus taisnstūrus. Terases neieskaita.")
    requested = int(st.number_input("Moduļu skaits", min_value=1, max_value=MAX_MODULES, value=1,
                                    step=1, key="ad_module_count"))
    # Noņemta moduļa apstiprinājums nedrīkst atgriezties, pievienojot moduli atpakaļ.
    confirmations = st.session_state.setdefault(CONFIRMATIONS_KEY, {})
    for stale in [i for i in confirmations if i >= requested]:
        del confirmations[stale]

    results = []
    for index in range(requested):
        data = _module_inputs(index, sources, pdf_id)
        if not data["confirmed"]:
            continue
        try:
            results.append(calculate_module(
                data["length"], data["width"], name=data["name"], source=data["source"],
                params=FrameParams(perimeter_width_mm=data["perimeter"]),
                nonstandard_confirmed=data["nonstandard"]))
        except ValueError as error:
            st.error(f"{data['name']}: {error}")

    for result in results:
        _render_module_result(result)

    if len(results) != requested:
        st.warning(f"**NEPILNS APRĒĶINS ({len(results)} no {requested} moduļiem).** Projekta "
                   "kopsumma un CSV eksports netiek rādīti, kamēr visi moduļi nav derīgi un "
                   "apstiprināti.")
        return

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
