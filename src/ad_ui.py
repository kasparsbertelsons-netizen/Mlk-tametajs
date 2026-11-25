"""Streamlit saskarne AD režīmam (Issue #4).

Plūsma: PDF (nav obligāts) → pagaidu teksta kandidāti un vektoru kandidāti (prototips,
`src/ad_vector.py`) ar avota lapu un priekšskatījumu → lietotājs ievada vai pārnes katra moduļa
L un W un spiež "Apstiprināt" → pamatrāmja aprēķins (`src/floor_frame.py`). Kandidāta L/W
pārnešana apstiprinājumu NEizdara un atceļ iepriekšējo apstiprinājumu (ievade mainās).

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
from src.ad_vector import CONSISTENT, analyze_pdf, render_preview_png
from src.floor_frame import (
    PERIMETER_WIDTH_MM, SCOPE_NOTE, WIDTH_REVIEW_LIMIT_MM, FrameParams,
    calculate_module, export_rows, scope_note, summarize_modules,
)
from src.frame_diagram import build_frame_svg
from src.reinforcement import (
    CONVENTION_NOTE, MAX_REINFORCEMENTS, RF_SOURCE_USER, ReinforcementError, format_axis, parse_axis,
)
from src.pdf_reader import read_pdf

MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_MODULES = 10
MANUAL_SOURCE = "Ievadīts manuāli"
SCAN_KEY = "ad_scan"                   # sesijas ietvaros; dzēšams
CONFIRMATIONS_KEY = "ad_confirmations"  # {moduļa indekss: ievades pirkstu nospiedums}


def parse_reinforcement_text(text):
    """(asis, kļūdas). Katra rinda vai komats/semikols/atstarpe atdala vienu asi (mm no moduļa gala).
    Nederīga ievade netiek ignorēta: tā tiek atgriezta kā kļūda un aprēķins netiek veikts."""
    axes, errors = [], []
    tokens = [t for t in (text or "").replace(";", "\n").replace(" ", "\n").splitlines() if t.strip()]
    # komats ir decimālzīme ("822,5"); tāpēc to NEuzskata par atdalītāju
    for token in tokens:
        try:
            axes.append(parse_axis(token))
        except ValueError as error:
            errors.append(f"\"{token[:20]}\": {error}")
    if len(axes) > MAX_REINFORCEMENTS:
        errors.append(f"Pārāk daudz pastiprinājumu (maks. {MAX_REINFORCEMENTS} vienam modulim).")
    return axes, errors


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
            try:   # vektoru prototips nedrīkst salauzt teksta kandidātus
                scan["vector"] = analyze_pdf(data, [page["page"] for page in scan["floor_pages"]])
                scan["vector_error"] = None
            except Exception as exc:
                scan["vector"], scan["vector_error"] = None, f"Vektoru analīze neizdevās: {exc}"
        except (ValueError, RuntimeError) as exc:
            error = f"PDF neizdevās nolasīt: {exc}"
        except Exception as exc:  # bojāts PDF u. c.
            error = f"PDF analīzes kļūda: {exc}"
    state[SCAN_KEY] = {"file_id": upload.file_id, "pdf_id": pdf_id, "scan": scan, "error": error}
    return scan, pdf_id, error


def _render_candidates(scan: dict, pdf_bytes=None):
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
    _render_vector_section(scan, pdf_bytes)


def _vector_source_label(candidate: dict) -> str:
    return f"PDF {candidate['page']}. lapa, vektoru kandidāts {candidate['id']}"


def _vector_candidates(scan) -> list:
    vector = (scan or {}).get("vector") or {}
    return [c for page in vector.get("pages", []) for c in page["candidates"]]


def _candidate_label(candidate: dict) -> str:
    size = f"{candidate['length_mm']}×{candidate['width_mm']} mm" if candidate["transferable"] \
        else "L/W netiek piedāvāti"
    return f"{candidate['id']}: {size}, {candidate['status']} (lapa {candidate['page']})"


def _transfer(candidate: dict, index: int):
    """Pārnes kandidāta L/W un avotu uz moduļa ievadi. Apstiprinājumu NEizdara un katrā pārnešanā DZĒŠ
    šī moduļa iepriekšējo apstiprinājumu (arī tad, ja pārnesta tā pati vērtība un nospiedums nemainītos)."""
    label = _vector_source_label(candidate)
    st.session_state[f"ad_L_{index}"] = int(candidate["length_mm"])
    st.session_state[f"ad_W_{index}"] = int(candidate["width_mm"])
    st.session_state[f"ad_src_{index}"] = label
    confirmations = st.session_state.get(CONFIRMATIONS_KEY)
    if confirmations is not None:
        confirmations.pop(index, None)
    count = int(st.session_state.get("ad_module_count", 1))
    others = [j + 1 for j in range(count) if j != index and st.session_state.get(f"ad_src_{j}") == label]
    text = (f"Kandidāts {candidate['id']} pārnests uz {index + 1}. moduli (L = {candidate['length_mm']} mm, "
            f"W = {candidate['width_mm']} mm). Apstiprinājums NAV izdarīts: pārbaudi un spied "
            "'Apstiprināt šo ievadi'.")
    if others:
        text += (f" BRĪDINĀJUMS: šis kandidāts jau ir izvēlēts {', '.join(map(str, others))}. modulim; viena "
                 "kandidāta ieskaitīšana divos moduļos tiek bloķēta.")
    st.session_state["ad_vec_notice"] = (text, bool(others))


def _render_vector_section(scan: dict, pdf_bytes):
    st.subheader("Vektoru ģeometrijas kandidāti (prototips)")
    st.caption("Prototips: kontūras un izmēru norādes tiek nolasītas no PDF vektoriem, un mērogs tiek "
               "pārbaudīts pret izmēru norādēm. Sintētisku paraugu rezultāts NAV pierādījums, ka tiks "
               "atpazīti reāli AD rasējumi, un pielaides ir tikai prototipa pielaides. Statuss "
               "'ģeometriski saskaņots' NEPIERĀDA konstrukcijas robežu. Kandidāti netiek apstiprināti "
               "automātiski; manuālā ievade paliek pieejama.")
    if scan.get("vector") is None:
        st.warning(scan.get("vector_error") or "Vektoru analīze nav pieejama.")
        return
    pages = scan["vector"]["pages"]
    for page in pages:
        if page["status"] != "ok":
            st.warning(f"{page['page']}. lapa: {page['notes'][0]}")
    candidates = _vector_candidates(scan)
    if not candidates:
        st.info("Vektoru kontūru kandidātu nav (nav kontūru ar izmēru norādēm). Ievadi L un W manuāli.")
    else:
        st.dataframe([{
            "Kandidāts": c["id"], "Lapa": c["page"], "Statuss": c["status"],
            "L (mm)": c["length_mm"] if c["transferable"] else None,
            "W (mm)": c["width_mm"] if c["transferable"] else None,
            "Mērogs": (f"1:{c['scale']['denominator']} ({c['scale']['status']})"
                       if c["scale"]["denominator"] else c["scale"]["status"]),
            "Moduļa marķējums": c["boundary"]["label"] or "",
            "Blakus": ", ".join(c["boundary"]["adjacent_to"]),
            "Problēmas": " | ".join(c["issues"])} for c in candidates],
            hide_index=True, use_container_width=True)
        labels = [_candidate_label(c) for c in candidates]
        picked = st.selectbox("Kandidāts (priekšskatījumam un pārnešanai)", labels, key="ad_vec_pick")
        candidate = candidates[labels.index(picked)]
        analysis = next(p for p in pages if p["page"] == candidate["page"])
        if pdf_bytes:
            try:
                st.image(render_preview_png(pdf_bytes, analysis, candidate["id"]),
                         caption=f"{candidate['page']}. lapa: izvēlētā kandidāta kontūra, izmēru teksti un "
                                 "avots. Zaļš = ģeometriski saskaņots/atpazīts, oranžs = neskaidrs, "
                                 "sarkans = atteikums, zils = izmēru teksts, pelēks raustīts = izslēgts "
                                 "(telpa, terase).")
            except Exception as exc:
                st.warning(f"Priekšskatījumu neizdevās izveidot: {exc}")
        with st.expander("Pierādījumi un problēmas (izvēlētais kandidāts)", expanded=True):
            st.markdown(f"**{candidate['id']}**, statuss: **{candidate['status']}**, "
                        f"lapa {candidate['page']}, avots: PDF vektori")
            for line in candidate["evidence"]:
                st.markdown(f"- {line}")
            for line in candidate["issues"]:
                st.markdown(f"- ⚠ {line}")
            st.caption(candidate["disclaimer"])
        if candidate["transferable"] and candidate["status"] == CONSISTENT:
            st.warning("Ģeometriski saskaņots nenozīmē konstruktīvi pierādītu grīdas rāmja robežu (var būt "
                       "fasādes kontūra): pārbaudi pret rasējumu pirms apstiprināt.")
        elif candidate["transferable"]:
            st.warning(f"Kandidāta statuss '{candidate['status']}': pierādījumu nepietiek (skat. problēmas). "
                       "Pārnešana atļauta ar brīdinājumu; pārbaudi L un W pret rasējumu.")
        count = int(st.session_state.get("ad_module_count", 1))
        target = st.selectbox("Pārnest uz moduli", list(range(1, count + 1)), key="ad_vec_target")
        st.button("Pārnest L un W uz moduli (neapstiprina)", key="ad_vec_transfer",
                  disabled=not candidate["transferable"], on_click=_transfer,
                  args=(candidate, int(target) - 1))
    notice = st.session_state.pop("ad_vec_notice", None)
    if notice:
        (st.warning if notice[1] else st.info)(notice[0])
    roles = [(p["page"], e) for p in pages for e in p["excluded"] if e["kind"] not in ("page_frame", "unmeasured")]
    unmeasured = sum(1 for p in pages for e in p["excluded"] if e["kind"] == "unmeasured")
    if roles or unmeasured:
        with st.expander("Izslēgtās kontūras (telpas, terases, ligzdotas kontūras)"):
            if roles:
                st.dataframe([{"Lapa": page, "Veids": e["kind"], "Marķējums": e.get("label") or "",
                               "Izmēri (mm)": ", ".join(str(v) for v in e.get("dimensions", [])),
                               "Iemesls": e["reason"]} for page, e in roles],
                             hide_index=True, use_container_width=True)
            st.caption(f"Kontūras bez piesaistītām izmēru norādēm (nav kandidāti): {unmeasured}.")


def _module_inputs(index: int, sources: list, pdf_id, vector_by_source: dict) -> dict:
    confirmations = st.session_state.setdefault(CONFIRMATIONS_KEY, {})
    with st.container(border=True):
        st.markdown(f"**Modulis {index + 1}**")
        name = st.text_input("Nosaukums", value=f"Modulis {index + 1}", max_chars=60,
                             key=f"ad_name_{index}")
        c1, c2, c3 = st.columns(3)
        length = c1.number_input("Garums L (mm)", min_value=0, max_value=100000,
                                 step=100, key=f"ad_L_{index}")
        width = c2.number_input("Platums W (mm)", min_value=0, max_value=100000,
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
        # --- pastiprinājumi 150×240: tikai lietotāja manuāla ievade un apstiprinājums (Issue #10) ---
        st.markdown("**Pastiprinājuma sijas 150×240 (nav obligāti)**")
        st.caption("Programma NEnosaka nesošās sienas un pastiprinājumus pati. Ja zini, ka vajag, ievadi sijas "
                   "CENTRA koordinātu. " + CONVENTION_NOTE + " Piemērs: 822,5 aizvieto pirmo regulāro sijas; "
                   "1150 pievieno papildus. Katra vērtība savā rindā. Tukšs lauks = tikai pamatrāmis "
                   "(tas NEpierāda, ka pastiprinājumi nav vajadzīgi).")
        rf_text = st.text_area("Pastiprinājumu asis (mm no moduļa gala), katra savā rindā", height=110,
                               key=f"ad_rf_{index}")
        rf_axes, rf_errors = parse_reinforcement_text(rf_text)
        for message in rf_errors:
            st.error(f"Pastiprinājumi: {message} Aprēķins šim modulim netiek veikts.")
        rf_key = tuple(rf_axes)
        rf_confirmed = False
        if rf_axes and not rf_errors:
            shown = ", ".join(format_axis(a) for a in sorted(set(rf_axes)))
            # Atslēga satur asis, L, W un perimetru: jebkura izmaiņa atceļ šī moduļa apstiprinājumu.
            digest = hashlib.sha256(repr((sorted(rf_key), int(length), int(width), int(perimeter))).encode()).hexdigest()[:12]
            rf_confirmed = st.checkbox(
                f"Apstiprinu pastiprinājumu pozīcijas (ass, mm no moduļa gala): {shown}",
                key=f"ad_rfok_{index}_{digest}")
            if not rf_confirmed:
                st.info("Pastiprinājumu pozīcijas gaida apstiprinājumu: aprēķins šim modulim netiek veikts.")
        # avots: ja L/W atšķiras no izvēlētā vektoru kandidāta, tas nav "tieši nolasīts"
        candidate = vector_by_source.get(source)
        effective = source
        if candidate and length and width and (int(length), int(width)) != (candidate["length_mm"],
                                                                         candidate["width_mm"]):
            effective = (f"{source}, MANUĀLI KORIĢĒTS (ievadīts {int(length)}×{int(width)} mm; kandidāts "
                         f"{candidate['length_mm']}×{candidate['width_mm']} mm)")
            st.warning(f"Ievadītie L/W ({int(length)}×{int(width)} mm) atšķiras no izvēlētā vektoru kandidāta "
                       f"{candidate['id']} ({candidate['length_mm']}×{candidate['width_mm']} mm): avots tiek "
                       "marķēts kā manuāli koriģēts, nevis tieši nolasīts.")
    return {"name": name.strip() or f"Modulis {index + 1}", "length": int(length),
            "width": int(width), "perimeter": int(perimeter), "source": source,
            "source_effective": effective, "candidate": candidate,
            "nonstandard": nonstandard, "confirmed": confirmed,
            "rf_axes": rf_axes, "rf_errors": rf_errors, "rf_confirmed": rf_confirmed}


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
    if result.reinforcements:
        st.caption(f"Pastiprinājumi: aizvieto {result.replaced_count}, papildus {result.added_count}; regulāras "
                   f"šķērssijas {result.regular_count} gab. Avots: {result.reinforcement_source}.")
    st.markdown("**Grīdas rāmja shēma** (mērogā; viena shēma = šī paša aprēķina ģeometrija)")
    st.markdown(build_frame_svg(result), unsafe_allow_html=True)
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
        _render_candidates(scan, upload.getvalue())
    vector_by_source = {_vector_source_label(c): c for c in _vector_candidates(scan) if c["transferable"]}
    sources = ([MANUAL_SOURCE] + [f"PDF {page['page']}. lapa" for page in (scan or {}).get("floor_pages", [])]
               + list(vector_by_source))

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
    claimed = {}          # vektoru kandidāts → pirmais modulis, kas to izmanto
    for index in range(requested):
        data = _module_inputs(index, sources, pdf_id, vector_by_source)
        if data["candidate"] is not None:
            first = claimed.setdefault(data["candidate"]["id"], index)
            if first != index:
                st.error(f"{data['name']}: vektoru kandidāts {data['candidate']['id']} jau ir izmantots "
                         f"{first + 1}. modulī. Viena kandidāta ieskaitīšana divos moduļos ir bloķēta; ja tie ir "
                         "divi atsevišķi moduļi, izvēlies avotu 'Ievadīts manuāli' un pārbaudi izmērus.")
                continue
        if not data["confirmed"]:
            continue
        if data["rf_errors"]:
            continue                       # kļūda jau parādīta; nepilns aprēķins netiek eksportēts
        if data["rf_axes"] and not data["rf_confirmed"]:
            continue
        try:
            results.append(calculate_module(
                data["length"], data["width"], name=data["name"], source=data["source_effective"],
                params=FrameParams(perimeter_width_mm=data["perimeter"]),
                nonstandard_confirmed=data["nonstandard"], reinforcements=data["rf_axes"],
                reinforcement_source=RF_SOURCE_USER))
        except ReinforcementError as error:
            for conflict in error.conflicts:
                st.error(f"{data['name']}: {conflict.message}")
            st.caption("Pilns aprēķins šim modulim ir bloķēts; programma neizdomā labojumu. Izlabo vai noņem ass.")
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
    reinforced = total["modules_with_reinforcements"] > 0
    st.subheader("Kopsavilkums (pamatrāmis + lietotāja pastiprinājumi)" if reinforced else "Kopsavilkums (tikai pamatrāmis)")
    x, y, z = st.columns(3)
    x.metric("Aprēķinātie moduļi", total["modules"])
    y.metric("Sijas kopā (gab.)", total["pieces"])
    z.metric("Kokmateriāli kopā", f"{total['volume_m3']:.5f} m³")
    if reinforced:
        st.caption(f"Regulāras šķērssijas: {total['regular']} gab.; pastiprinājumi: aizvieto {total['replaced']}, "
                   f"papildus {total['added']} (lietotāja norādīti, nav nolasīti no PDF).")
    st.dataframe([{"Modulis": r.name, "L (mm)": r.length_mm, "W (mm)": r.width_mm,
                   "Sijas (gab.)": r.total_pieces, "m³": r.total_volume_m3,
                   "Atlikums (mm)": r.remainder_mm, "Jāpārbauda": "JĀ" if r.needs_review else "",
                   "Avots": r.source} for r in results], hide_index=True, use_container_width=True)
    if total["needs_review"]:
        st.warning(f"Moduļi ar atzīmi 'jāpārbauda': {total['needs_review']}.")
    st.warning(scope_note(reinforced))

    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerows(export_rows(results))
    st.download_button("Lejupielādēt pamatrāmja tabulu (CSV Excel)", "﻿" + buffer.getvalue(),
                       file_name="MLK_AD_pamatramis.csv", mime="text/csv")
