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
    BASES, CONSTRUCTIONS, DRIVERS, LAYER_GROUPS, MANUAL_GROUPS, NOT_FINAL, STAGE_NOTE, ST_DUP, UNITS, default_layers,
    empty_project, estimate, export_rows, module_fp,
)

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


def _table(project, key, columns, config, numeric=(), boolean=(), label=None, help_text=None):
    ver = st.session_state.get(VER, 0)
    df = pd.DataFrame(project.get(key) or [], columns=columns)
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in boolean:
        df[col] = df[col].fillna(False).astype(bool)
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
    if st.session_state.pop("bp_switch_notice", None):
        st.warning("Konstrukcijas tips mainīts: slāņu saraksts aizstāts ar attiecīgā tipa noklusējumu (iepriekšējie slāņu labojumi zaudēti).")

    with st.expander("1. Moduļi (grīdas rāmis — esošais kodols)", expanded=not project["modules"]):
        st.caption("Katrs modulis ir taisnstūris ar APSTIPRINĀTIEM L un W (mm). Atzīmē «Apstiprināts»; mainot L, W vai asis, "
                   "apstiprinājums tiek atcelts. Pastiprinājumu asis (nav obligāti): mm no moduļa gala, atdalītas ar atstarpi "
                   "(skat. docs/FLOOR_FRAME_REINFORCEMENT.md). Neapstiprināti moduļi netiek skaitīti.")
        _table(project, "modules", ["name", "length_mm", "width_mm", "axes", "confirmed"], {
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
        _table(project, "terraces", ["name", "area_m2"], {"name": st.column_config.TextColumn("Terase"),
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
                                   "waste_pct": _clean(rec["waste_pct"]), "article": _clean(rec["article"]), "source": _clean(rec["source"]) or ""}

    wall_cfg = {"name": st.column_config.TextColumn("Posms"),
                "length_m": st.column_config.NumberColumn("Garums (m)", min_value=0.0),
                "height_mm": st.column_config.NumberColumn("Augstums (mm) — tukšs = noklusējums", min_value=0)}
    with st.expander("3. Ārsienas (faktiskie garumi)", expanded=False):
        st.caption("Ievadi FAKTISKO ārējo sienu garumus. Kopīgās moduļu šuves NAV fasāde: neieraksti tās; programma salīdzina ar "
                   "moduļu perimetru.")
        _number("Noklusējuma sienu augstums (mm) — orientējošs, rediģējams", project, ("wall_height_mm",), step=50.0)
        _table(project, "ext_walls", ["name", "length_m", "height_mm"], wall_cfg, numeric=("length_m", "height_mm"))
        if project.get("construction") == "frame":
            _frame_inputs(project, "ext", "Ārsienu karkass (nav apstiprināts, ja nav zināms)")

    with st.expander("4. Iekšsienas", expanded=False):
        _table(project, "int_walls", ["name", "length_m", "height_mm"], wall_cfg, numeric=("length_m", "height_mm"))
        if project.get("construction") == "frame":
            _frame_inputs(project, "int", "Iekšsienu karkass (nav apstiprināts, ja nav zināms)")

    with st.expander("5. Logi un durvis (atveres atskaita attiecīgajā sienu grupā)", expanded=False):
        _table(project, "openings", ["kind", "name", "width_mm", "height_mm", "count", "wall"], {
            "kind": st.column_config.SelectboxColumn("Veids", options=["Logs", "Durvis"]),
            "name": st.column_config.TextColumn("Marķējums"),
            "width_mm": st.column_config.NumberColumn("Platums (mm)", min_value=0),
            "height_mm": st.column_config.NumberColumn("Augstums (mm)", min_value=0),
            "count": st.column_config.NumberColumn("Skaits", min_value=0, step=1),
            "wall": st.column_config.SelectboxColumn("Siena", options=["Ārsiena", "Iekšsiena"])},
            numeric=("width_mm", "height_mm", "count"))

    with st.expander("6. Jumts", expanded=False):
        roof = project["roof"]
        mode = st.radio("Jumta seguma platība", ["Ievadu faktisko platību", "Slīpuma aprēķins (jāapstiprina)"], horizontal=False,
                        index=1 if roof.get("mode") == "slope" else 0, key=f"bp_roofmode_{ver}")
        roof["mode"] = "slope" if mode.startswith("Slīpuma") else "area"
        if roof["mode"] == "area":
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
        layers = pd.DataFrame(project.get("layers") or [], columns=["enabled", "group", "name", "basis", "unit", "thickness_mm",
                                                                  "step_mm", "waste_pct", "approved", "article", "source"])
        layers["basis"] = layers["basis"].map(BASES).fillna(layers["basis"])
        for col in ("thickness_mm", "step_mm", "waste_pct"):
            layers[col] = pd.to_numeric(layers[col], errors="coerce")
        layers["enabled"] = layers["enabled"].fillna(True).astype(bool)
        layers["approved"] = layers["approved"].fillna(False).astype(bool)
        edited = st.data_editor(layers, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"bp_layers_{ver}",
                                column_config={
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

    with st.expander("8. Receptes — patēriņa normas (stiprinājumi, lentes, MEP u.c.)", expanded=False):
        st.caption("Katra recepte: materiāls × PATĒRIŅA NORMA uz izvēlēto pamatu (m², m, gab.) VAI tiešs daudzums. Normas nav izdomātas: "
                   "tukša norma = «nav ievadīts». Artikuls (ja ir katalogā) aizpilda nosaukumu, specifikāciju, vienību un iepakojumu. "
                   "«Ražošanas posms» ir brīvs lauks — klasifikācija netiek izstrādāta.")
        recipes = pd.DataFrame(project.get("recipes") or [], columns=["enabled", "group", "article", "name", "spec", "unit", "driver",
                                                                      "norm", "qty", "waste_pct", "pack_size", "module", "stage",
                                                                      "approved", "source"])
        recipes["driver"] = recipes["driver"].map(DRIVERS).fillna(recipes["driver"])
        for col in ("norm", "qty", "waste_pct", "pack_size"):
            recipes[col] = pd.to_numeric(recipes[col], errors="coerce")
        recipes["enabled"] = recipes["enabled"].fillna(True).astype(bool)
        recipes["approved"] = recipes["approved"].fillna(False).astype(bool)
        edited = st.data_editor(recipes, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"bp_recipes_{ver}",
                                column_config={
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
            "approved": st.column_config.CheckboxColumn("Apstiprināts"), "source": st.column_config.TextColumn("Avots / pieņēmums")})
        recs = _records(edited, boolean=("enabled", "approved"))
        for rec in recs:
            rec["driver"] = LABEL_TO_DRIVER.get(rec.get("driver"), rec.get("driver") or "direct")
        project["recipes"] = recs

    with st.expander("9. Materiālu katalogs (artikuli, cenas)", expanded=False):
        st.caption("Neobligāts katalogs: viena cena un iepakojums artikulam attiecas uz VISĀM rindām ar šo artikulu (cena tiek piemērota, "
                   "ja katalogā un rindā vienība sakrīt). Sasaiste ar MLK/Moneo artikuliem — nākamajos posmos; šeit tikai teksts.")
        _table(project, "catalog", ["article", "name", "spec", "unit", "unit_price", "pack_size", "source"], {
            "article": st.column_config.TextColumn("Artikuls"), "name": st.column_config.TextColumn("Nosaukums"),
            "spec": st.column_config.TextColumn("Specifikācija"), "unit": st.column_config.TextColumn("Vienība"),
            "unit_price": st.column_config.NumberColumn("Cena par vienību (EUR)", min_value=0.0),
            "pack_size": st.column_config.NumberColumn("Iepakojums", min_value=0.0),
            "source": st.column_config.TextColumn("Avots")}, numeric=("unit_price", "pack_size"))

    with st.expander("10. Manuālās rindas, citas izmaksas, pārbaude", expanded=False):
        st.caption("Manuāla materiāla rinda neautomatizētam apjomam (vannasistaba, MEP u.c.) — marķēta «manuāli».")
        _table(project, "manual", ["group", "article", "material", "spec", "qty", "unit", "waste_pct", "pack_size", "module", "stage",
                                   "approved", "source"], {
            "group": st.column_config.SelectboxColumn("Grupa", options=MANUAL_GROUPS),
            "article": st.column_config.TextColumn("Artikuls"), "material": st.column_config.TextColumn("Materiāls"),
            "spec": st.column_config.TextColumn("Specifikācija"),
            "qty": st.column_config.NumberColumn("Daudzums", min_value=0.0),
            "unit": st.column_config.TextColumn("Vienība"),
            "waste_pct": st.column_config.NumberColumn("Rezerve %", min_value=0.0),
            "pack_size": st.column_config.NumberColumn("Iepakojums", min_value=0.0),
            "module": st.column_config.TextColumn("Modulis/telpa/sistēma"), "stage": st.column_config.TextColumn("Ražošanas posms"),
            "approved": st.column_config.CheckboxColumn("Apstiprināts"),
            "source": st.column_config.TextColumn("Avots")}, numeric=("qty", "waste_pct", "pack_size"), boolean=("approved",))
        st.markdown("**Citas izmaksas (EUR)** — tukšs = NAV ievadīts, NAV iekļauts budžetā")
        _table(project, "other_costs", ["name", "amount_eur"], {"name": st.column_config.TextColumn("Izmaksu pozīcija"),
               "amount_eur": st.column_config.NumberColumn("Summa (EUR)", min_value=0.0)}, numeric=("amount_eur",))
        text = st.text_area("Šajā tāmē NEIEKĻAUTIE darbi (katrs savā rindā)", value="\n".join(project.get("excluded", [])),
                            key=f"bp_excl_{ver}", height=110)
        project["excluded"] = [line.strip() for line in text.splitlines() if line.strip()]
        st.markdown("**Atbildīgās personas pārbaude** (iepirkumu saraksts nav «gatavs» bez tās un bez obligāto grupu pārklājuma)")
        review = project.setdefault("review", {"reviewer": "", "confirmed": False})
        review["reviewer"] = st.text_input("Pārbaudītāja vārds", value=review.get("reviewer") or "", key=f"bp_rev_{ver}", max_chars=60)
        review["confirmed"] = st.checkbox("Apstiprinu, ka esmu pārbaudījis šo sarakstu", value=bool(review.get("confirmed")),
                                          key=f"bp_revok_{ver}")

    est = estimate(project)
    with result_box:
        _render_result(project, est)


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
    st.markdown("**Budžeta kopsavilkums** (tikai ievadītās cenas)")
    b1, b2 = st.columns(2)
    b1.metric("Materiāli (rindas ar cenu)", f"{bud['materials']:.2f} EUR" if bud["priced_rows"] else "cenas nav ievadītas")
    b2.metric("Kopā ar citām izmaksām", f"{bud['total']:.2f} EUR" + (" — NEPILNS" if bud["incomplete"] else "") if (bud["priced_rows"] or bud["other_entered"]) else "nav ievadīts")
    if bud["incomplete"]:
        notes = []
        if bud["unpriced_rows"]:
            notes.append(f"bez cenas {bud['unpriced_rows']} rindas")
        if bud["other_missing"]:
            notes.append("neievadītas izmaksas: " + ", ".join(bud["other_missing"]))
        if est.uncovered:
            notes.append("obligātās grupas bez datiem: " + ", ".join(est.uncovered))
        st.warning("Budžets ir NEPILNS: " + "; ".join(notes) + ". Neievadīts nav nulle.")
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

    with st.expander("Cenas un darba stundas (neobligāti, manuāli; atstāj tukšu, ja nav zināms)"):
        rows = [r for r in est.rows if r.qty is not None and r.status != ST_DUP]
        df = pd.DataFrame([{"Grupa": r.group, "Materiāls": r.material, "Pasūtāmais": round(r.order_qty, 3), "Vienība": r.unit,
                            "Cena par vienību (EUR)": (project.get("prices") or {}).get(r.price_key(), {}).get("price"),
                            "Darba stundas": r.hours} for r in rows],
                          columns=["Grupa", "Materiāls", "Pasūtāmais", "Vienība", "Cena par vienību (EUR)", "Darba stundas"])
        for col in ("Cena par vienību (EUR)", "Darba stundas"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        edited = st.data_editor(df, hide_index=True, use_container_width=True, disabled=["Grupa", "Materiāls", "Pasūtāmais", "Vienība"],
                                key=f"bp_prices_{st.session_state.get(VER, 0)}")
        new = {}
        for r, rec in zip(rows, edited.to_dict("records")):
            price, hours = _clean(rec["Cena par vienību (EUR)"]), _clean(rec["Darba stundas"])
            if price is not None or hours is not None:
                new[r.price_key()] = {"price": price, "hours": hours}
        if new != project.get("prices"):
            project["prices"] = new
            st.rerun()
        st.caption("Cenas un stundas ir TIKAI jūsu ievadītās; programma tās neizdomā. Šeit nav MLK cenu.")

    with st.expander("Kontroles aprēķini"):
        for name, value, ok in est.checks:
            st.write(("✅ " if ok else "❌ ") + f"{name}: {value}")
        for key, label in (("floor_frame_m2", "Moduļu laukums Σ L×W (m²)"), ("pir_free_m2", "PIR brīvo zonu laukums (m²)"),
                           ("openings_ext_m2", "Ārsienu atveres (m²)"), ("openings_int_m2", "Iekšsienu atveres (m²)")):
            if key in est.areas:
                st.write(f"• {label}: {est.areas[key]:g}")
    if est.excluded:
        st.error("**NAV IEKĻAUTS šajā tāmē:** " + "; ".join(est.excluded))

    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerows(export_rows(project.get("name") or "Projekts", est))
    st.download_button("Lejupielādēt tāmi (CSV Excel)", "﻿" + buffer.getvalue(), file_name="MLK_visas_ekas_tame.csv",
                       mime="text/csv", key="bp_csv")
