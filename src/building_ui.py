"""Streamlit skats «Pilnas ēkas tāme» (Issue #12). Vertikāls, telefonam draudzīgs: sadaļas ir izvēršamas, rezultāti augšā.

Projekta dati glabājas TIKAI šīs sesijas `st.session_state` (nekas netiek sūtīts uz āru vai saglabāts); aprēķins ir
`src/building_estimate.py`. Visi ievaddati ir lietotāja ievadīti; demonstrācijas projekts ir sintētisks.
"""
import csv
import io
import math

import pandas as pd
import streamlit as st

from src.building_demo import DEMO_NAME, demo_project
from src.building_estimate import (
    BASES, COST_CATEGORIES, CONSTRUCTIONS, DRIVERS, GROUPS, LAYER_GROUPS, LINE_LISTS, MANUAL_GROUPS, NOT_FINAL, STAGE_NOTE, ST_DUP,
    UNITS, confirm_review, default_layers, empty_project, ensure_ids, estimate, export_rows, module_fp, project_fingerprint,
)
from src.ad_pdf_ui import render_ad_import
from src.building_demo import demo_ad_project
from src.building_estimate import DETAIL_LEVELS, COST_SCOPES, TYPE_APPLIES, TYPE_KINDS
from src.control_ui import render_control
from src.catalog_import import (
    apply_catalog, catalog_template_csv, catalog_template_xlsx, diff_catalog, parse_catalog_file,
)
from src.project_io import LOCAL_DATA_REMINDER, export_project, import_project
from src.xlsx_export import build_workbook

KEY = "bp_project"
VER = "bp_version"
BASIS_LABELS = list(BASES.values())
DRIVER_LABELS = list(DRIVERS.values())
LABEL_TO_DRIVER = {v: k for k, v in DRIVERS.items()}
CLT_ROWS = [("ext", "CLT ārsienu paneļi"), ("int", "CLT iekšsienu paneļi"), ("roof", "CLT jumta paneļi"), ("floor", "CLT grīdas paneļi")]
LABEL_TO_BASIS = {v: k for k, v in BASES.items()}


def _project():
    if KEY not in st.session_state:
        st.session_state[KEY] = empty_project()
        st.session_state[VER] = 0
    return st.session_state[KEY]


def _load_demo():
    st.session_state[KEY] = demo_project()
    st.session_state[VER] = st.session_state.get(VER, 0) + 1


def _load_ad_demo():
    st.session_state[KEY] = demo_ad_project()
    st.session_state[VER] = st.session_state.get(VER, 0) + 1


def _clear():
    st.session_state[KEY] = empty_project()
    st.session_state[VER] = st.session_state.get(VER, 0) + 1


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value.item() if hasattr(value, "item") else value


def _records(df, numeric=(), boolean=()):
    out = []
    for rec in df.to_dict("records"):
        rec = {k: _clean(v) for k, v in rec.items()}
        for b in boolean:
            rec[b] = bool(rec.get(b))
        if all(v in (None, False) for v in rec.values()):
            continue                        # tukša rinda
        out.append(rec)
    return out


def _obj(df, skip):
    """Tekstu kolonnas → object (tukša kolonna nedrīkst kļūt par float; Streamlit tipu saderība)."""
    for col in df.columns:
        if col not in skip:
            df[col] = df[col].astype(object)
    return df


def _table(project, key, columns, config, numeric=(), boolean=(), label=None, help_text=None, bool_true=()):
    ver = st.session_state.get(VER, 0)
    if key in LINE_LISTS:                                   # stabila rindas identitāte (slēpta kolonna)
        columns = ["id"] + list(columns)
        config = {**config, "id": None}
    df = pd.DataFrame(project.get(key) or [], columns=columns)
    for col in df.columns:
        if col not in numeric and col not in boolean:
            df[col] = df[col].astype(object)                  # tukšas teksta kolonnas nedrīkst kļūt par float (Streamlit tipu pārbaude)
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in boolean:
        df[col] = df[col].fillna(col in bool_true).astype(bool)
    if help_text:
        st.caption(help_text)
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, use_container_width=True, column_config=config,
                            key=f"bp_{key}_{ver}")
    project[key] = _records(edited, numeric, boolean)


def _number(label, project, path, **kw):
    ver = st.session_state.get(VER, 0)
    node = project
    for part in path[:-1]:
        node = node[part]
    current = node.get(path[-1])
    node[path[-1]] = st.number_input(label, value=None if current is None else float(current), min_value=0.0,
                                     key=f"bp_{'_'.join(path)}_{ver}", **kw)


def _sync_module_confirmations(project):
    """Apstiprinājums ir piesaistīts L, W un asīm: mainoties jebkuram, tas tiek atcelts (A → B → A neatjaunojas)."""
    fps = project.setdefault("module_fp", {})
    cancelled = []
    for i, m in enumerate(project.get("modules", [])):
        key, now = str(i), module_fp(m)
        if m.get("confirmed"):
            if fps.get(key) is None:
                fps[key] = now
            elif fps[key] != now:
                m["confirmed"] = False
                fps.pop(key, None)
                cancelled.append(m.get("name") or f"Modulis {i + 1}")
        else:
            fps.pop(key, None)
    for stale in [k for k in fps if int(k) >= len(project.get("modules", []))]:
        del fps[stale]
    return cancelled


def render_building_mode():
    project = _project()
    ver = st.session_state.get(VER, 0)
    st.info("**Pilnas ēkas PROVIZORISKA materiālu tāme.** Ievadi apstiprinātus izmērus vai ielādē sintētisku demonstrāciju. "
            "Programma neizdomā trūkstošus izmērus, MLK receptes, cenas vai normstundas. " + NOT_FINAL + ".")
    c1, c2 = st.columns(2)
    c1.button("Ielādēt demonstrācijas projektu", key="bp_demo", on_click=_load_demo, use_container_width=True,
              help="Sintētisks projekts: nav reāls MLK projekts, cenas vai rasējumi.")
    c2.button("Notīrīt projektu", key="bp_clear", on_click=_clear, use_container_width=True)
    st.button("Ielādēt AD demonstrāciju (no sintētiska AD PDF)", key="bp_demo_ad", on_click=_load_ad_demo, use_container_width=True,
              help="Sintētisks AD PDF → apstiprināti kandidāti → AD tipu receptes → pilnībā cenota tāme.")
    notice_box = st.container()                  # FIKSĒTS konteiners: pārejoši paziņojumi nedrīkst nobīdīt sadaļas (citādi izvēršamās sadaļas aizveras)
    with notice_box:
        if st.session_state.get("bp_notice"):
            st.success(st.session_state.pop("bp_notice"))
    result_box = st.container()

    project["name"] = st.text_input("Projekta nosaukums", value=project.get("name") or "", max_chars=80, key=f"bp_name_{ver}")
    st.caption(STAGE_NOTE)
    labels = list(CONSTRUCTIONS.values())
    current = project.get("construction", "clt")
    choice = st.radio("Konstrukcijas tips (vienota aplikācija, atšķirīgas receptes)", labels,
                      index=list(CONSTRUCTIONS).index(current) if current in CONSTRUCTIONS else 0, key=f"bp_constr_{ver}")
    chosen = list(CONSTRUCTIONS)[labels.index(choice)]
    if chosen != current:
        project["construction"] = chosen
        project["layers"] = default_layers(chosen)          # CLT un karkasa slāņu saraksti atšķiras
        st.session_state["bp_switch_notice"] = chosen
        st.rerun()
    switch_box = st.container()
    with switch_box:
        if st.session_state.pop("bp_switch_notice", None):
            st.warning("Konstrukcijas tips mainīts: slāņu saraksts aizstāts ar attiecīgā tipa noklusējumu (iepriekšējie slāņu labojumi zaudēti).")

    stage = project.get("stage", "AD")
    st.caption(f"Projekta stadija: **{ {'AD': 'AD prognoze (sākotnējā)', 'PD': 'PD detalizācija (atvasināta kopija)', 'kalibrēta': 'Kalibrētā versija (atvasināta kopija)'}.get(stage, stage) }**. "
               "AD tāme tiek nodalīta no vēlākās PD detalizācijas un faktiskajiem datiem.")
    with st.expander("0. AD PDF → tāmes ievaddati (kandidāti ar apstiprināšanu)", expanded=False):
        render_ad_import(project, ver, KEY, VER)

    with st.expander("1. Moduļi (grīdas rāmis — esošais kodols)", expanded=not project["modules"]):
        st.caption("Katrs modulis ir taisnstūris ar APSTIPRINĀTIEM L un W (mm). Atzīmē «Apstiprināts»; mainot L, W vai asis, "
                   "apstiprinājums tiek atcelts. Pastiprinājumu asis (nav obligāti): mm no moduļa gala, atdalītas ar atstarpi "
                   "(skat. docs/FLOOR_FRAME_REINFORCEMENT.md). Neapstiprināti moduļi netiek skaitīti.")
        _table(project, "modules", ["name", "length_mm", "width_mm", "axes", "confirmed", "source_key"], {
            "source_key": None,                                                  # moduļa avota identitāte (slēpta; netiek zaudēta rediģējot)
            "name": st.column_config.TextColumn("Modulis"),
            "length_mm": st.column_config.NumberColumn("L (mm)", min_value=0, step=100),
            "width_mm": st.column_config.NumberColumn("W (mm)", min_value=0, step=100),
            "axes": st.column_config.TextColumn("Pastiprinājumu asis (mm)"),
            "confirmed": st.column_config.CheckboxColumn("Apstiprināts"),
        }, numeric=("length_mm", "width_mm"), boolean=("confirmed",))
        cancelled = _sync_module_confirmations(project)
        if cancelled:
            st.session_state["bp_cancel_notice"] = cancelled      # tiek parādīts nākamajā (atkārtotajā) izpildē
            st.rerun()
        for name in st.session_state.pop("bp_cancel_notice", []):
            st.warning(f"Apstiprinājums atcelts (mainīts L, W vai asis): {name}. Atzīmē «Apstiprināts» vēlreiz.")
        pir = project["pir"]
        pir["enabled"] = st.checkbox("PIR siltinājums brīvajās zonās starp sijām", value=pir.get("enabled", True), key=f"bp_pir_on_{ver}")
        _number("PIR biezums (mm)", project, ("pir", "thickness_mm"), step=10.0)

    with st.expander("2. Platības un terases", expanded=False):
        st.caption("Neto iekštelpu platība un griestu platība jāievada (netiek minēta). Terases tiek skaitītas atsevišķi, "
                   "NE iekštelpu platībā.")
        _number("Neto grīdas platība (m²)", project, ("floor_net_m2",), step=1.0)
        _number("Griestu platība (m²)", project, ("ceiling_m2",), step=1.0)
        _table(project, "terraces", ["name", "article", "area_m2"], {"name": st.column_config.TextColumn("Terase"),
               "article": st.column_config.TextColumn("Artikuls"),
               "area_m2": st.column_config.NumberColumn("Platība (m²)", min_value=0.0)}, numeric=("area_m2",))

    if project.get("construction") == "clt":
        with st.expander("2b. CLT paneļi (biezums jāievada un jāapstiprina)", expanded=False):
            st.caption("Ārsienu/iekšsienu CLT paneļi: neto laukums (bez atverēm) × biezums → m² un m³. Cena tiek piesaistīta TIKAI "
                       "izvēlētajai vienībai (m² vai m³), otra vienība tiek rādīta bet netiek cenota (nedubultot izmaksas). CLT rezerve "
                       "ir regulējama atsevišķi (10% ir provizorisks pieņēmums). Biezumi nav izdomāti: tukšs = «nav ievadīts». "
                       "Atgriezumu/optimizācijas algoritms nav realizēts.")
            project["floor_frame_enabled"] = st.checkbox("Šim projektam ir koka grīdas pamatrāmis (esošais rāmja kodols)",
                                                         value=project.get("floor_frame_enabled", True), key=f"bp_ffe_{ver}")
            clt = project.setdefault("clt", {})
            df = pd.DataFrame([{"key": k, "Paneļi": label, "enabled": bool((clt.get(k) or {}).get("enabled")),
                                "thickness_mm": (clt.get(k) or {}).get("thickness_mm"),
                                "thickness_confirmed": bool((clt.get(k) or {}).get("thickness_confirmed")),
                                "price_unit": (clt.get(k) or {}).get("price_unit") or "m²",
                                "waste_pct": (clt.get(k) or {}).get("waste_pct"), "article": (clt.get(k) or {}).get("article"),
                                "source": (clt.get(k) or {}).get("source")} for k, label in CLT_ROWS])
            for col in ("thickness_mm", "waste_pct"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            edited = st.data_editor(df, hide_index=True, use_container_width=True, key=f"bp_clt_{ver}",
                                    disabled=["key", "Paneļi"], column_order=["Paneļi", "enabled", "thickness_mm", "thickness_confirmed",
                                                                              "price_unit", "waste_pct", "article", "source"],
                                    column_config={"enabled": st.column_config.CheckboxColumn("Ieskaitīt"),
                                                   "thickness_mm": st.column_config.NumberColumn("Biezums (mm)", min_value=0.0),
                                                   "thickness_confirmed": st.column_config.CheckboxColumn("Biezums apstiprināts"),
                                                   "price_unit": st.column_config.SelectboxColumn("Cena pēc", options=["m²", "m³"]),
                                                   "waste_pct": st.column_config.NumberColumn("Rezerve %", min_value=0.0, max_value=100.0),
                                                   "article": st.column_config.TextColumn("Artikuls"),
                                                   "source": st.column_config.TextColumn("Avots")})
            for rec in edited.to_dict("records"):
                clt[rec["key"]] = {"enabled": bool(rec["enabled"]), "thickness_mm": _clean(rec["thickness_mm"]),
                                   "thickness_confirmed": bool(rec["thickness_confirmed"]), "price_unit": rec["price_unit"] or "m²",
                                   "waste_pct": _clean(rec["waste_pct"]), "article": _clean(rec["article"]), "source": _clean(rec["source"]) or "",
                                   "articles": (clt.get(rec["key"]) or {}).get("articles") or {}}      # artikuli pa biezumiem (AD) netiek zaudēti

    wall_cfg = {"name": st.column_config.TextColumn("Posms"),
                "length_m": st.column_config.NumberColumn("Garums (m)", min_value=0.0),
                "height_mm": st.column_config.NumberColumn("Augstums (mm) — tukšs = noklusējums", min_value=0),
                "type": st.column_config.TextColumn("Konstr. tips (kods)"),
                "clt_mm": st.column_config.NumberColumn("CLT biezums (mm), neobligāti", min_value=0.0)}
    WALL_COLS = ["name", "length_m", "height_mm", "type", "clt_mm"]
    with st.expander("3. Ārsienas (faktiskie garumi)", expanded=False):
        st.caption("Ievadi FAKTISKO ārējo sienu garumus. Kopīgās moduļu šuves NAV fasāde: neieraksti tās; programma salīdzina ar "
                   "moduļu perimetru.")
        _number("Noklusējuma sienu augstums (mm) — orientējošs, rediģējams", project, ("wall_height_mm",), step=50.0)
        _table(project, "ext_walls", WALL_COLS, wall_cfg, numeric=("length_m", "height_mm", "clt_mm"))
        st.markdown("**Zelmiņi** (trīsstūra gala sienas): laukums = ½ × pamats × augstums; ieskaitīti ārsienu bruto laukumā")
        _table(project, "gables", ["name", "base_m", "height_m", "type", "clt_mm"], {
            "name": st.column_config.TextColumn("Zelmiņš"), "base_m": st.column_config.NumberColumn("Pamats (m)", min_value=0.0),
            "height_m": st.column_config.NumberColumn("Augstums (m)", min_value=0.0), "type": st.column_config.TextColumn("Konstr. tips"),
            "clt_mm": st.column_config.NumberColumn("CLT biezums (mm)", min_value=0.0)}, numeric=("base_m", "height_m", "clt_mm"))
        if project.get("construction") == "frame":
            _frame_inputs(project, "ext", "Ārsienu karkass (nav apstiprināts, ja nav zināms)")

    with st.expander("4. Iekšsienas", expanded=False):
        _table(project, "int_walls", WALL_COLS, wall_cfg, numeric=("length_m", "height_mm", "clt_mm"))
        if project.get("construction") == "frame":
            _frame_inputs(project, "int", "Iekšsienu karkass (nav apstiprināts, ja nav zināms)")

    with st.expander("5. Logi un durvis (atveres atskaita attiecīgajā sienu grupā)", expanded=False):
        st.caption("Atveres: ārējās, iekšējās un JUMTA atsevišķi. «Posms» (neobligāti) piesaista atveri konkrētai sienai/slīpnei (atskaitīšana pa tipiem/CLT biezumiem). "
                   "Viena un tā pati atvere (nosaukums+izmērs+siena+posms) netiek atskaitīta divreiz.")
        _table(project, "openings", ["kind", "name", "article", "width_mm", "height_mm", "count", "wall", "segment"], {
            "article": st.column_config.TextColumn("Artikuls"), "segment": st.column_config.TextColumn("Posms/slīpne"),
            "kind": st.column_config.SelectboxColumn("Veids", options=["Logs", "Durvis"]),
            "name": st.column_config.TextColumn("Marķējums"),
            "width_mm": st.column_config.NumberColumn("Platums (mm)", min_value=0),
            "height_mm": st.column_config.NumberColumn("Augstums (mm)", min_value=0),
            "count": st.column_config.NumberColumn("Skaits", min_value=0, step=1),
            "wall": st.column_config.SelectboxColumn("Siena", options=["Ārsiena", "Iekšsiena", "Jumts"])},
            numeric=("width_mm", "height_mm", "count"))

    with st.expander("6. Jumts", expanded=False):
        roof = project["roof"]
        modes = ["Ievadu faktisko platību", "Slīpuma aprēķins (jāapstiprina)", "Slīpnes (divslīpju jumts, AD)"]
        mode = st.radio("Jumta bruto platība", modes, horizontal=False,
                        index={"slope": 1, "slopes": 2}.get(roof.get("mode"), 0), key=f"bp_roofmode_{ver}")
        roof["mode"] = {1: "slope", 2: "slopes"}.get(modes.index(mode), "area")
        if roof["mode"] == "slopes":
            st.caption("Katra slīpne: bruto laukums = garums × horizontālā projekcija / cos(leņķis) VAI tieši ievadīts laukums; apstiprini katru slīpni. "
                       "CLT biezums var atšķirties pa slīpnēm. Jumta logi (sadaļa 5, siena = Jumts) tiek atskaitīti VIENREIZ → neto laukums.")
            _table(project, "roof_slopes", ["name", "length_m", "projection_m", "angle_deg", "area_m2", "type", "clt_mm", "confirmed"], {
                "name": st.column_config.TextColumn("Slīpne"), "length_m": st.column_config.NumberColumn("Garums (m)", min_value=0.0),
                "projection_m": st.column_config.NumberColumn("Horiz. projekcija (m)", min_value=0.0),
                "angle_deg": st.column_config.NumberColumn("Leņķis (°)", min_value=0.0),
                "area_m2": st.column_config.NumberColumn("Bruto laukums (m²) — tieši", min_value=0.0),
                "type": st.column_config.TextColumn("Konstr. tips"), "clt_mm": st.column_config.NumberColumn("CLT biezums (mm)", min_value=0.0),
                "confirmed": st.column_config.CheckboxColumn("Apstiprināts")}, numeric=("length_m", "projection_m", "angle_deg", "area_m2", "clt_mm"),
                boolean=("confirmed",))
        elif roof["mode"] == "area":
            _number("Jumta seguma faktiskā platība (m²)", project, ("roof", "area_m2"), step=1.0)
        else:
            _number("Jumta projekcijas (plāna) laukums (m²), ieskaitot izbīdes", project, ("roof", "footprint_m2"), step=1.0)
            _number("Jumta leņķis (°)", project, ("roof", "angle_deg"), step=1.0)
            roof["slope_confirmed"] = st.checkbox("Apstiprinu slīpuma aprēķinu (platība = projekcija / cos leņķis)",
                                                  value=bool(roof.get("slope_confirmed")), key=f"bp_roofok_{ver}")
        _frame_inputs(project, "roof", "Jumta spāres (neobligāti CLT projektā; provizoriski, solis = attālums starp spārēm)")

    with st.expander("7. Konstrukciju slāņi (pa grupām)", expanded=False):
        st.caption("Slāņu nosaukumi ir tikai ieteikumi. m³ prasa biezumu, m (piem. latojums) prasa soli mm; tukšs = «nav ievadīts». "
                   "Rezerve % pēc noklusējuma 10, nošķirta no neto. Viens un tas pats slānis (nosaukums + pamats) netiek ieskaitīts divreiz.")
        layers = pd.DataFrame(project.get("layers") or [], columns=["id", "enabled", "group", "name", "basis", "unit", "thickness_mm",
                                                                  "step_mm", "waste_pct", "approved", "article", "source"])
        layers["basis"] = layers["basis"].map(BASES).fillna(layers["basis"])
        for col in ("thickness_mm", "step_mm", "waste_pct"):
            layers[col] = pd.to_numeric(layers[col], errors="coerce")
        _obj(layers, ("enabled", "approved", "thickness_mm", "step_mm", "waste_pct"))
        layers["enabled"] = layers["enabled"].fillna(True).astype(bool)
        layers["approved"] = layers["approved"].fillna(False).astype(bool)
        edited = st.data_editor(layers, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"bp_layers_{ver}",
                                column_config={
            "id": None,
            "enabled": st.column_config.CheckboxColumn("Ieskaitīt"),
            "group": st.column_config.SelectboxColumn("Grupa", options=LAYER_GROUPS),
            "name": st.column_config.TextColumn("Slānis"),
            "basis": st.column_config.SelectboxColumn("Pamats", options=BASIS_LABELS),
            "unit": st.column_config.SelectboxColumn("Vienība", options=UNITS),
            "thickness_mm": st.column_config.NumberColumn("Biezums (mm)", min_value=0.0),
            "step_mm": st.column_config.NumberColumn("Solis (mm)", min_value=0.0),
            "waste_pct": st.column_config.NumberColumn("Rezerve %", min_value=0.0, max_value=100.0),
            "approved": st.column_config.CheckboxColumn("Apstiprināts"),
            "article": st.column_config.TextColumn("Artikuls"),
            "source": st.column_config.TextColumn("Avots / pieņēmums")})
        recs = _records(edited, boolean=("enabled", "approved"))
        for rec in recs:
            rec["basis"] = LABEL_TO_BASIS.get(rec.get("basis"), rec.get("basis"))
        project["layers"] = recs

    with st.expander("7b. Konstrukciju tipi un to materiālu receptes (AD)", expanded=False):
        st.caption("Tipu režīmā (ārsienas/iekšsienas/jumts) slāņus dod konstrukciju tipu receptes: vairākas latojuma kārtas, plāksnes, siltinājums, apdares un stiprinājumu "
                   "normas pa tipiem. Tipa laukums = piesaistīto posmu neto laukumi. CLT slānis tikai norāda posma CLT biezumu (materiāla rindu veido CLT recepte — nav "
                   "dubultošanas). Normas/cenas NAV izdomātas: tukšs = «nav ievadīts». Manuālais režīms (globālie slāņi, sadaļa 7) paliek.")
        modes = ["Manuāli: globālie slāņi (sadaļa 7)", "Pēc konstrukciju tipiem (7b)"]
        picked = st.radio("Slāņu režīms ārsienām/iekšsienām/jumtam", modes, index=1 if project.get("layers_mode") == "types" else 0, key=f"bp_lmode_{ver}")
        project["layers_mode"] = "types" if picked == modes[1] else "manual"
        _table(project, "construction_types", ["code", "name", "applies_to", "source"], {
            "code": st.column_config.TextColumn("Kods"), "name": st.column_config.TextColumn("Nosaukums"),
            "applies_to": st.column_config.SelectboxColumn("Attiecas uz", options=list(TYPE_APPLIES)),
            "source": st.column_config.TextColumn("Avots")})
        _table(project, "type_recipes", ["enabled", "type", "name", "kind", "unit", "thickness_mm", "step_mm", "norm", "article", "spec", "waste_pct", "pack_size",
                                          "approved", "detail", "assumption", "source"], {
            "enabled": st.column_config.CheckboxColumn("Ieskaitīt"), "type": st.column_config.TextColumn("Tips"),
            "name": st.column_config.TextColumn("Slānis"), "kind": st.column_config.SelectboxColumn("Veids", options=TYPE_KINDS),
            "unit": st.column_config.TextColumn("Vienība (m²/m³/m/gab.)"),
            "thickness_mm": st.column_config.NumberColumn("Biezums (mm)", min_value=0.0), "step_mm": st.column_config.NumberColumn("Solis (mm)", min_value=0.0),
            "norm": st.column_config.NumberColumn("Norma uz m² (reizinātājs/patēriņš)", min_value=0.0), "article": st.column_config.TextColumn("Artikuls"),
            "spec": st.column_config.TextColumn("Specifikācija"), "waste_pct": st.column_config.NumberColumn("Rezerve %", min_value=0.0),
            "pack_size": st.column_config.NumberColumn("Iepakojums", min_value=0.0), "approved": st.column_config.CheckboxColumn("Apstiprināts"),
            "detail": st.column_config.SelectboxColumn("Detalizācija", options=DETAIL_LEVELS), "assumption": st.column_config.TextColumn("AD pieņēmums"),
            "source": st.column_config.TextColumn("Avots")}, numeric=("thickness_mm", "step_mm", "norm", "waste_pct", "pack_size"),
            boolean=("enabled", "approved"), bool_true=("enabled",))

    with st.expander("8. Receptes — patēriņa normas (stiprinājumi, lentes, MEP u.c.)", expanded=False):
        st.caption("Katra recepte: materiāls × PATĒRIŅA NORMA uz izvēlēto pamatu (m², m, gab.) VAI tiešs daudzums. Normas nav izdomātas: "
                   "tukša norma = «nav ievadīts». Artikuls (ja ir katalogā) aizpilda nosaukumu, specifikāciju, vienību un iepakojumu. "
                   "«Ražošanas posms» ir brīvs lauks — klasifikācija netiek izstrādāta.")
        recipes = pd.DataFrame(project.get("recipes") or [], columns=["id", "enabled", "group", "article", "name", "spec", "unit", "driver",
                                                                      "norm", "qty", "waste_pct", "pack_size", "module", "stage",
                                                                      "approved", "detail", "assumption", "cost_scope", "source"])
        recipes["driver"] = recipes["driver"].map(DRIVERS).fillna(recipes["driver"])
        for col in ("norm", "qty", "waste_pct", "pack_size"):
            recipes[col] = pd.to_numeric(recipes[col], errors="coerce")
        _obj(recipes, ("enabled", "approved", "norm", "qty", "waste_pct", "pack_size"))
        recipes["enabled"] = recipes["enabled"].fillna(True).astype(bool)
        recipes["approved"] = recipes["approved"].fillna(False).astype(bool)
        edited = st.data_editor(recipes, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"bp_recipes_{ver}",
                                column_config={
            "id": None,
            "enabled": st.column_config.CheckboxColumn("Ieskaitīt"),
            "group": st.column_config.SelectboxColumn("Grupa", options=MANUAL_GROUPS),
            "article": st.column_config.TextColumn("Artikuls"), "name": st.column_config.TextColumn("Materiāls"),
            "spec": st.column_config.TextColumn("Specifikācija"), "unit": st.column_config.TextColumn("Vienība"),
            "driver": st.column_config.SelectboxColumn("Pamats", options=DRIVER_LABELS),
            "norm": st.column_config.NumberColumn("Norma uz pamata vienību", min_value=0.0),
            "qty": st.column_config.NumberColumn("Tiešs daudzums", min_value=0.0),
            "waste_pct": st.column_config.NumberColumn("Rezerve % (tukšs = noklusējums)", min_value=0.0),
            "pack_size": st.column_config.NumberColumn("Iepakojums", min_value=0.0),
            "module": st.column_config.TextColumn("Modulis/telpa/sistēma"), "stage": st.column_config.TextColumn("Ražošanas posms"),
            "approved": st.column_config.CheckboxColumn("Apstiprināts"),
            "detail": st.column_config.SelectboxColumn("Detalizācija (AD: komplekts/norma)", options=DETAIL_LEVELS),
            "assumption": st.column_config.TextColumn("AD pieņēmums (obligāts komplektam/normai)"),
            "cost_scope": st.column_config.SelectboxColumn("Izmaksu segums", options=COST_SCOPES),
            "source": st.column_config.TextColumn("Avots / pieņēmums")})
        recs = _records(edited, boolean=("enabled", "approved"))
        for rec in recs:
            rec["driver"] = LABEL_TO_DRIVER.get(rec.get("driver"), rec.get("driver") or "direct")
        project["recipes"] = recs

    with st.expander("9. Materiālu katalogs un cenu imports (XLSX/CSV)", expanded=False):
        _catalog_section(project)

    with st.expander("10. Manuālās rindas, neiekļautie darbi", expanded=False):
        st.caption("Manuāla materiāla rinda neautomatizētam apjomam (vannasistaba, MEP materiāli u.c.) — marķēta «manuāli». "
                   "Darba stundas šeit NEievada (sadaļa 11), lai darbs netiktu ieskaitīts divreiz.")
        _table(project, "manual", ["group", "article", "material", "spec", "qty", "unit", "waste_pct", "pack_size", "module", "stage",
                                   "approved", "detail", "assumption", "cost_scope", "source"], {
            "detail": st.column_config.SelectboxColumn("Detalizācija", options=DETAIL_LEVELS),
            "assumption": st.column_config.TextColumn("AD pieņēmums"),
            "cost_scope": st.column_config.SelectboxColumn("Izmaksu segums", options=COST_SCOPES),
            "group": st.column_config.SelectboxColumn("Grupa", options=MANUAL_GROUPS),
            "article": st.column_config.TextColumn("Artikuls"), "material": st.column_config.TextColumn("Materiāls"),
            "spec": st.column_config.TextColumn("Specifikācija"),
            "qty": st.column_config.NumberColumn("Daudzums", min_value=0.0),
            "unit": st.column_config.TextColumn("Vienība"),
            "waste_pct": st.column_config.NumberColumn("Rezerve % (tukšs = noklusējums)", min_value=0.0),
            "pack_size": st.column_config.NumberColumn("Iepakojums", min_value=0.0),
            "module": st.column_config.TextColumn("Modulis/telpa/sistēma"), "stage": st.column_config.TextColumn("Ražošanas posms"),
            "approved": st.column_config.CheckboxColumn("Apstiprināts"),
            "source": st.column_config.TextColumn("Avots")}, numeric=("qty", "waste_pct", "pack_size"), boolean=("approved",))
        text = st.text_area("Šajā tāmē NEIEKĻAUTIE darbi (katrs savā rindā)", value="\n".join(project.get("excluded", [])),
                            key=f"bp_excl_{ver}", height=110)
        project["excluded"] = [line.strip() for line in text.splitlines() if line.strip()]

    with st.expander("11. Darba operācijas un darba pašizmaksas likme", expanded=False):
        st.caption("Darba izmaksas = stundas × PILNA darba pašizmaksas likme (EUR/h). Stundas: normstundas uz vienību × apjoms (pamats no "
                   "ģeometrijas vai tiešs daudzums) VAI tiešas stundas — nekad abas. Ražošanas posms ir brīvs lauks (klasifikāciju "
                   "lietotājs definēs vēlāk). Trūkstoši dati tiek marķēti, nulle netiek pieņemta.")
        labour = project.setdefault("labour", {"rate_eur_h": None, "operations": []})
        _number("Pilna darba pašizmaksas likme (EUR/h)", project, ("labour", "rate_eur_h"), step=1.0)
        ops = pd.DataFrame(labour.get("operations") or [], columns=["id", "enabled", "group", "name", "stage", "module", "driver", "qty",
                                                                    "unit", "norm_h", "hours", "rate_eur_h", "approved", "source"])
        ops["driver"] = ops["driver"].map(DRIVERS).fillna(ops["driver"])
        for col in ("qty", "norm_h", "hours", "rate_eur_h"):
            ops[col] = pd.to_numeric(ops[col], errors="coerce")
        _obj(ops, ("enabled", "approved", "qty", "norm_h", "hours", "rate_eur_h"))
        ops["enabled"] = ops["enabled"].fillna(True).astype(bool)
        ops["approved"] = ops["approved"].fillna(False).astype(bool)
        edited = st.data_editor(ops, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"bp_ops_{ver}", column_config={
            "id": None, "enabled": st.column_config.CheckboxColumn("Ieskaitīt"),
            "group": st.column_config.SelectboxColumn("Grupa", options=GROUPS), "name": st.column_config.TextColumn("Darba operācija"),
            "stage": st.column_config.TextColumn("Ražošanas posms"), "module": st.column_config.TextColumn("Modulis"),
            "driver": st.column_config.SelectboxColumn("Apjoma pamats", options=DRIVER_LABELS),
            "qty": st.column_config.NumberColumn("Tiešs apjoms (ja pamats «tiešs»)", min_value=0.0),
            "unit": st.column_config.TextColumn("Vienība"),
            "norm_h": st.column_config.NumberColumn("Normstundas uz vienību", min_value=0.0),
            "hours": st.column_config.NumberColumn("TIEŠAS stundas (bez normas)", min_value=0.0),
            "rate_eur_h": st.column_config.NumberColumn("Likme EUR/h (tukšs = kopējā)", min_value=0.0),
            "approved": st.column_config.CheckboxColumn("Apstiprināts"), "source": st.column_config.TextColumn("Avots")})
        recs = _records(edited, boolean=("enabled", "approved"))
        for rec in recs:
            rec["driver"] = LABEL_TO_DRIVER.get(rec.get("driver"), rec.get("driver") or "direct")
        labour["operations"] = recs

    with st.expander("12. Citas izmaksas, pieskaitāmās, cenojums un PVN", expanded=False):
        st.caption("Manuālās izmaksas (ārpakalpojumi, transports, montāža) ir ATSEVIŠĶI no materiāliem un darba operācijām. Ārpakalpojums ar "
                   "norādītu grupu, kurā jau ir darba operācijas, tiek bloķēts kā dubultošana. Tukšs = NAV ievadīts, nav iekļauts.")
        _table(project, "other_costs", ["name", "category", "group", "amount_eur", "source"], {
            "name": st.column_config.TextColumn("Izmaksu pozīcija"),
            "category": st.column_config.SelectboxColumn("Kategorija", options=COST_CATEGORIES),
            "group": st.column_config.SelectboxColumn("Grupa (neobligāti)", options=GROUPS),
            "amount_eur": st.column_config.NumberColumn("Summa (EUR bez PVN)", min_value=0.0),
            "source": st.column_config.TextColumn("Avots")}, numeric=("amount_eur",))
        pricing = project.setdefault("pricing", {})
        _number("Pieskaitāmās izmaksas (% no tiešajām izmaksām)", project, ("pricing", "overhead_pct"), step=0.5)
        methods = ["Nav izvēlēts", "Uzcenojums (cena = pašizmaksa × (1 + u))", "Peļņas marža (cena = pašizmaksa / (1 − m))"]
        current = {"markup": 1, "margin": 2}.get(pricing.get("method"), 0)
        choice = st.radio("Cenojuma metode (DIVAS atšķirīgas formulas)", methods, index=current, key=f"bp_method_{ver}")
        pricing["method"] = [None, "markup", "margin"][methods.index(choice)]
        if pricing["method"] == "markup":
            _number("Uzcenojums (% no pašizmaksas)", project, ("pricing", "markup_pct"), step=0.5)
        elif pricing["method"] == "margin":
            _number("Peļņas marža (% no pārdošanas cenas; < 100)", project, ("pricing", "margin_pct"), step=0.5)
        pricing["vat_enabled"] = st.checkbox("Aprēķināt PVN", value=bool(pricing.get("vat_enabled")), key=f"bp_vat_on_{ver}")
        if pricing["vat_enabled"]:
            _number("PVN likme (%)", project, ("pricing", "vat_pct"), step=1.0)

    with st.expander("13. Projekta saglabāšana un atjaunošana (JSON)", expanded=False):
        _project_io_section(project)

    # atbildīgās personas pārbaude: attiecas uz KONKRĒTU datu stāvokli (pirkstu nospiedums); jebkura vēlāka izmaiņa to atceļ
    ensure_ids(project)
    review = project.setdefault("review", {"reviewer": "", "confirmed": False, "fp": None})
    with st.expander("14. Atbildīgās personas pārbaude", expanded=False):
        st.caption("Iepirkumu saraksts nav «gatavs» bez šīs pārbaudes UN obligāto grupu pārklājuma. Pārbaude attiecas uz pašreizējiem datiem: "
                   "jebkura datu izmaiņa to atceļ.")
        valid = bool(review.get("confirmed")) and review.get("fp") == project_fingerprint(project)
        if review.get("confirmed") and not valid:
            st.warning("Dati mainīti pēc pārbaudes: apstiprinājums atcelts. Apstiprini vēlreiz.")
        who = st.text_input("Pārbaudītāja vārds", value=review.get("reviewer") or "", key=f"bp_rev_{ver}", max_chars=60)
        ok = st.checkbox("Apstiprinu, ka esmu pārbaudījis šo sarakstu", value=valid, key=f"bp_revok_{ver}_{project_fingerprint(project)}")
        if ok and who.strip():
            if not valid:
                confirm_review(project, who)
        elif not ok:
            project["review"] = {"reviewer": who.strip(), "confirmed": False, "fp": None}
        else:
            st.info("Ievadi pārbaudītāja vārdu.")

    est = estimate(project)
    with result_box:
        _render_result(project, est)


def _catalog_section(project):
    st.caption("Cenu imports tikai LOKĀLI (fails tiek lasīts atmiņā, netiek sūtīts). Kolonnas: Artikuls, Nosaukums, Specifikācija, Mērvienība, "
               "Vienības cena EUR BEZ PVN, Iepakojums, Piegādātājs (pēc izvēles). Artikuls = teksts; trūkstoša cena = tukša (nav nulle); "
               "mērvienības netiek konvertētas; formulas netiek izpildītas.")
    c1, c2 = st.columns(2)
    c1.download_button("Parauga šablons (XLSX, DEMO)", catalog_template_xlsx(), file_name="MLK_katalogs_sablons.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="bp_tpl_xlsx", use_container_width=True)
    c2.download_button("Parauga šablons (CSV, DEMO)", catalog_template_csv(), file_name="MLK_katalogs_sablons.csv", mime="text/csv",
                       key="bp_tpl_csv", use_container_width=True)
    upload = st.file_uploader("Augšupielādē cenu katalogu (.xlsx vai .csv)", type=["xlsx", "csv"], key=f"bp_cat_up_{st.session_state.get(VER, 0)}")
    if upload is not None:
        result = parse_catalog_file(upload.name, upload.getvalue())
        for row_no, message in result.errors:
            st.error((f"Rinda {row_no}: " if row_no else "") + message)
        for row_no, message in result.warnings[:30]:
            st.warning((f"Rinda {row_no}: " if row_no else "") + message)
        if not result.fatal:
            st.write(f"Nolasītas {result.read_rows} rindas: derīgas **{len(result.rows)}**, ar kļūdām {len(result.errors)} (netiks importētas).")
            used = {}
            for r in estimate(project).rows:
                if r.article:
                    used.setdefault(r.article, set()).add(r.unit)
            diff = diff_catalog(project.get("catalog") or [], result.rows, used)
            st.write(f"Jauni artikuli: {len(diff['new'])}; atjaunināmi: {len(diff['updated'])}; nemainīti: {len(diff['unchanged'])}.")
            if diff["unmatched"]:
                st.info("Nesaistīti artikuli (neviena tāmes rinda tos nelieto): " + ", ".join(diff["unmatched"][:30]))
            if diff["unknown_in_file"]:
                st.warning("Tāmes rindu artikuli, kuru NAV failā un katalogā (cena netiks piemērota): " + ", ".join(diff["unknown_in_file"][:30]))
            for art, unit, units in diff["unit_conflicts"]:
                st.error(f"Artikuls «{art}»: failā mērvienība «{unit}», bet tāmes rindā {units} — cena netiks piemērota (konversijas netiek veiktas).")
            st.dataframe([{"Artikuls": r["article"], "Nosaukums": r["name"], "Specifikācija": r["spec"], "Vienība": r["unit"],
                           "Cena EUR": r["unit_price"], "Iepakojums": r["pack_size"], "Piegādātājs": r["supplier"]}
                          for r in result.rows[:200]], hide_index=True, use_container_width=True)
            confirm = st.checkbox(f"Apstiprinu piemērot {len(result.rows)} importētās rindas katalogam", key=f"bp_cat_ok_{upload.file_id}")
            if st.button("Piemērot katalogam", key="bp_cat_apply", disabled=not (confirm and result.rows)):
                skipped = apply_catalog(project, result.rows, used)
                st.session_state["bp_notice"] = (f"Katalogam piemērotas {len(result.rows) - len(skipped)} rindas."
                                                 + (f" Izlaistas {len(skipped)} (mērvienība neatbilst tāmes rindām): "
                                                    + ", ".join(a for a, _u, _v in skipped[:20]) if skipped else ""))
                st.rerun()
    _table(project, "catalog", ["article", "name", "spec", "unit", "unit_price", "pack_size", "supplier", "source"], {
        "article": st.column_config.TextColumn("Artikuls"), "name": st.column_config.TextColumn("Nosaukums"),
        "spec": st.column_config.TextColumn("Specifikācija"), "unit": st.column_config.TextColumn("Vienība"),
        "unit_price": st.column_config.NumberColumn("Cena EUR bez PVN par vienību", min_value=0.0),
        "pack_size": st.column_config.NumberColumn("Iepakojums", min_value=0.0),
        "supplier": st.column_config.TextColumn("Piegādātājs"),
        "source": st.column_config.TextColumn("Avots")}, numeric=("unit_price", "pack_size"))


def _project_io_section(project):
    st.warning(LOCAL_DATA_REMINDER)
    st.download_button("Lejupielādēt projektu (JSON)", export_project(project), file_name="MLK_projekts.json", mime="application/json",
                       key="bp_json_dl")
    st.caption("Fails satur ievaddatus, katalogu, receptes, darbaspēku un cenas (bez PDF). Netiek sūtīts automātiski. Imports validē failu un "
               "NEuzticas gatavības statusam: atbildīgās personas pārbaude jāapstiprina no jauna.")
    up = st.file_uploader("Atjaunot projektu no JSON", type=["json"], key=f"bp_json_up_{st.session_state.get(VER, 0)}")
    if up is not None:
        result = import_project(up.getvalue())
        for error in result.errors:
            st.error("Imports neizdevās: " + error)
        for notice in result.notices:
            st.warning(notice)
        if result.project is not None and not result.errors:
            st.success(f"Fails derīgs: «{result.project.get('name')}», moduļi {len(result.project.get('modules', []))}.")
            if st.button("Atjaunot šo projektu", key="bp_json_apply"):
                st.session_state[KEY] = result.project
                st.session_state[VER] = st.session_state.get(VER, 0) + 1
                st.session_state["bp_notice"] = "Projekts atjaunots. Atbildīgās personas pārbaude jāapstiprina no jauna."
                st.rerun()


def _f(value):
    return None if value is None else float(value)


def _frame_inputs(project, key, title):
    st.markdown(f"**{title}**")
    ver = st.session_state.get(VER, 0)
    a, b, c = st.columns(3)
    for col, field, label in ((a, "b_mm", "b (mm)"), (b, "h_mm", "h (mm)"), (c, "step_mm", "Solis (mm)")):
        project["frames"][key][field] = col.number_input(label, value=_f(project["frames"][key].get(field)), min_value=0.0, step=5.0,
                                                          key=f"bp_fr_{key}_{field}_{ver}")


def _render_result(project, est):
    st.subheader("Tāmes rezultāts")
    if est.errors:
        for e in est.errors:
            st.error(e)
    if not est.complete:
        st.warning("**NEPILNA TĀME.** Trūkst ievaddatu vai ir kļūdas; trūkstošie lielumi NAV aizvietoti ar pieņēmumiem. "
                   "Neizmanto kā piedāvājumu.")
    else:
        st.warning("Pamata ievaddati ievadīti, bet tāme joprojām ir PROVIZORISKA: biezumi, normas un slāņu parametri ir lietotāja "
                   "ievadīti pieņēmumi, nav MLK recepšu un cenu. Nav gala piedāvājums.")
    for group, items in est.missing.items():
        with st.expander(f"Nepilna sadaļa: {group} ({len(items)})"):
            for item in items:
                st.write("• " + item)
    for w in est.warnings:
        st.warning(w)
    if not est.rows:
        st.info("Tāme ir tukša. Spied «Ielādēt demonstrācijas projektu» vai ievadi datus zemāk.")
        return

    summary = est.summary()
    bud = est.budget()
    st.markdown("**Budžets** (EUR bez PVN; tikai ievadītie lielumi)")
    if project.get("is_demo"):
        st.warning("DEMO: visi skaitļi ir sintētiski (nav MLK cenas, normas vai reāls projekts).")
    pr = est.pricing or {}
    lines = [("Materiāli (pasūtāmais × cena)", bud["materials"] if bud["priced_rows"] else None),
             (f"Darbs ({bud['labour_hours']:.1f} h × likme)", bud["labour_cost"] if bud["labour_rows"] else None),
             ("Ārpakalpojumi", bud["by_category"]["Ārpakalpojumi"]), ("Transports", bud["by_category"]["Transports"]),
             ("Montāža", bud["by_category"]["Montāža"]), ("Citas izmaksas", bud["by_category"]["Cits"]),
             ("TIEŠĀS IZMAKSAS", bud["direct"]), (f"Pieskaitāmās ({pr.get('overhead_pct') if pr.get('overhead_pct') is not None else 'nav'} %)", bud["overhead"]),
             ("PAŠIZMAKSA", bud["cost_total"]),
             {"markup": f"Uzcenojums {pr.get('markup_pct')} % (cena = pašizmaksa × (1+u))",
              "margin": f"Peļņas marža {pr.get('margin_pct')} % (cena = pašizmaksa / (1−m))"}.get(bud["method"], "Uzcenojums/marža nav izvēlēta"),
             ("PĀRDOŠANAS CENA bez PVN", bud["sell"]), ("PVN", bud["vat"] if pr.get("vat_enabled") else None),
             ("SUMMA AR PVN", bud["total_incl"])]
    rows_out = []
    for item in lines:
        if isinstance(item, str):
            rows_out.append({"Pozīcija": item, "EUR": None})
        else:
            rows_out.append({"Pozīcija": item[0], "EUR": None if item[1] is None else round(item[1], 2)})
    st.dataframe(rows_out, hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    c1.metric("Pašizmaksa", f"{bud['cost_total']:.2f} EUR" + (" — NEPILNA" if bud["incomplete"] else ""))
    c2.metric("Pārdošanas cena bez PVN", ("nav aprēķināta" if bud["sell"] is None else f"{bud['sell']:.2f} EUR")
              + (" — NEPILNA" if bud["incomplete"] and bud["sell"] is not None else ""))
    if bud["incomplete"]:
        st.warning("Budžets ir NEPILNS — NAV gala piedāvājums: " + "; ".join(bud["reasons"]) + ". Neievadīts nav nulle.")
    else:
        st.success("Visi budžeta lielumi ievadīti, bet tas joprojām ir PROVIZORISKS (AD stadija; nav 90% precizitātes apliecinājuma).")
    if bud["unapproved_rows"]:
        st.caption(f"Nav apstiprinātas rindas: {bud['unapproved_rows']} (lietotāja ievadīti/provizoriski parametri).")
    st.info("**Iepirkuma gatavība:** " + est.procurement_status)
    st.markdown("**Kopsavilkums pa grupām**")
    st.dataframe([{"Grupa": s["group"], "Statuss": s["status"], "Rindas": s["rows"], "Nav ievadīts": s["not_entered"],
                   "Koksne neto m³": round(s["timber_net"], 3), "Koksne pasūt. m³": round(s["timber_order"], 3),
                   "Izmaksas EUR": None if s["cost"] is None else round(s["cost"], 2),
                   "Darba st.": s["hours"]} for s in summary], hide_index=True, use_container_width=True)
    t_net, t_order = sum(s["timber_net"] for s in summary), sum(s["timber_order"] for s in summary)
    m1, m2 = st.columns(2)
    m1.metric("Koksne kopā (neto)", f"{t_net:.3f} m³")
    m2.metric("Koksne pasūtāmā (ar rezervi)", f"{t_order:.3f} m³")
    st.caption("Koksne = rāmja koks + CLT paneļi (m³). Dažādu materiālu daudzumi netiek summēti.")

    st.markdown("**Materiālu tabula**")
    table = [{"Materiāls": r.material, "Neto": None if r.qty is None else round(r.qty, 3), "Vienība": r.unit,
              "Pasūtāmais": None if r.order_qty is None else round(r.order_qty, 3), "Grupa": r.group, "Statuss": r.status,
              "Apstiprinājums": r.approval, "Artikuls": r.article, "Specifikācija": r.spec, "Rezerve %": r.waste_pct,
              "Iepakojums": r.pack_size, "Modulis/sistēma": r.module, "Ražošanas posms": r.stage,
              "Alt. vienība (nav cenota)": None if r.alt_qty is None else f"{r.alt_qty:.3f} {r.alt_unit}",
              "Pamats": r.basis, "Avots/pieņēmums": r.source, "Piezīme": r.note} for r in est.rows]
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.caption("Pasūtāmais = neto × (1 + rezerve). Rezerve NAV neto daudzums. «gab.» tiek noapaļots uz augšu.")

    with st.expander("Cenas pa rindām (neobligāti; EUR bez PVN par vienību)"):
        rows = [r for r in est.rows if r.qty is not None and r.status != ST_DUP]
        prices = project.get("prices") or {}
        df = pd.DataFrame([{"Grupa": r.group, "Materiāls": r.material, "Artikuls": r.article, "Specifikācija": r.spec, "Pasūtāmais": round(r.order_qty, 3),
                            "Vienība": r.unit, "Cena (EUR/vienība)": (prices.get(r.row_id) or {}).get("price"),
                            "Cena no kataloga": r.unit_price if (prices.get(r.row_id) or {}).get("price") is None else None} for r in rows],
                          columns=["Grupa", "Materiāls", "Artikuls", "Specifikācija", "Pasūtāmais", "Vienība", "Cena (EUR/vienība)", "Cena no kataloga"])
        for col in ("Cena (EUR/vienība)", "Cena no kataloga"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        edited = st.data_editor(df, hide_index=True, use_container_width=True,
                                disabled=["Grupa", "Materiāls", "Artikuls", "Specifikācija", "Pasūtāmais", "Vienība", "Cena no kataloga"],
                                key=f"bp_prices_{st.session_state.get(VER, 0)}")
        new = {}
        for r, rec in zip(rows, edited.to_dict("records")):
            price = _clean(rec["Cena (EUR/vienība)"])
            if price is not None:                                   # cena piesaistīta STABILAI rindas identitātei + vienībai/artikulam/specifikācijai
                new[r.row_id] = {"price": price, "sig": r.sig}
        kept = {k: v for k, v in prices.items() if k not in {r.row_id for r in rows}}      # rindas, kas šobrīd neaprēķinās, netiek zaudētas
        new.update(kept)
        if new != prices:
            project["prices"] = new
            st.rerun()
        st.caption("Cenas ir TIKAI jūsu ievadītās; programma tās neizdomā. Cena tiek piesaistīta konkrētai rindai (un tās vienībai/artikulam/"
                   "specifikācijai): vienādi nosaukumi ar atšķirīgu specifikāciju nepārņem svešu cenu. Kataloga cenas ņemamas no artikula.")

    with st.expander("Iepirkumu saraksts (BOM; rindas netiek apvienotas)"):
        proc = [{"Artikuls": r.article, "Specifikācija": r.spec, "Materiāls": r.material, "Vienība": r.unit,
                 "Neto": None if r.qty is None else round(r.qty, 3), "Rezerve %": r.waste_pct,
                 "Pasūtāmais": None if r.order_qty is None else round(r.order_qty, 3), "Iepakojums": r.pack_size,
                 "Cena": r.unit_price, "Modulis": r.module, "Posms": r.stage, "Statuss": r.status if r.qty is not None else "NAV IEVADĪTS",
                 "Grupa": r.group} for r in sorted(est.rows, key=lambda x: (x.group, x.article or "~", x.material))
                if r.status != ST_DUP and not r.group.startswith("Terases")]
        st.dataframe(proc, hide_index=True, use_container_width=True)
        st.caption("Saraksts ir AD stadijas provizorisks. " + est.procurement_status)

    if est.labour:
        with st.expander("Darba operācijas (stundas un izmaksas)"):
            st.dataframe([{"Grupa": x.group, "Darbs": x.name, "Posms": x.stage, "Stundas": None if x.hours is None else round(x.hours, 2),
                           "Likme": x.rate, "Izmaksas": None if x.cost is None else round(x.cost, 2), "Statuss": x.status}
                          for x in est.labour], hide_index=True, use_container_width=True)

    with st.expander("Kontroles aprēķini"):
        for name, value, ok in est.checks:
            st.write(("✅ " if ok else "❌ ") + f"{name}: {value}")
        for key, label in (("floor_frame_m2", "Moduļu laukums Σ L×W (m²)"), ("pir_free_m2", "PIR brīvo zonu laukums (m²)"),
                           ("openings_ext_m2", "Ārsienu atveres (m²)"), ("openings_int_m2", "Iekšsienu atveres (m²)")):
            if key in est.areas:
                st.write(f"• {label}: {est.areas[key]:g}")
    if est.excluded:
        st.error("**NAV IEKĻAUTS šajā tāmē:** " + "; ".join(est.excluded))

    with st.expander("15. Prognozes versijas un faktiskā kontrole (lokāli)", expanded=False):
        render_control(project, est, st.session_state.get(VER, 0), KEY, VER)

    st.markdown("**Lejupielādes**")
    xlsx = build_workbook(project, est)
    st.download_button("Lejupielādēt Excel (XLSX): kopsavilkums, tāme, iepirkumi, darbs, klienta piedāvājums", xlsx,
                       file_name="MLK_visas_ekas_tame.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="bp_xlsx", use_container_width=True)
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerows(export_rows(project.get("name") or "Projekts", est))
    st.download_button("Lejupielādēt BOM (CSV)", "\ufeff" + buffer.getvalue(), file_name="MLK_visas_ekas_tame.csv",
                       mime="text/csv", key="bp_csv", use_container_width=True)
    st.download_button("Saglabāt projektu (JSON)", export_project(project), file_name="MLK_projekts.json", mime="application/json",
                       key="bp_json_dl2", use_container_width=True)
    st.caption(LOCAL_DATA_REMINDER)
