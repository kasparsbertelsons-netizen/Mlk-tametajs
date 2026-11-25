"""Sintētisks demonstrācijas projekts (Issue #12). Visi skaitļi ir izdomāti; nav MLK dati, cenas vai reāli rasējumi.

Ēka: divi taisnstūra moduļi 12000×4000 un 8000×4000, novietoti galu pie gala (kopīgā šuve 4000 mm gar abām malām —
fasādē NETIEK skaitīta). Ārsienu garums = 2×(20+4) = 48 m, nevis moduļu perimetru summa 56 m.
Karkasa šķērsgriezumi, soļi, biezumi un cenas ir DEMONSTRĀCIJAS vērtības, nevis MLK receptes.
"""
from src.building_estimate import (
    G_ELEC, G_EQUIP, G_EXT, G_FASTEN, G_FINISH, G_FLOOR, G_INT, G_PLUMB, G_ROOF, G_SANIT, G_VENT, default_layers, empty_project,
    module_fp,
)

DEMO_NAME = "DEMO — sintētiska CLT moduļu māja (nav reāls projekts)"
DEMO_FRAME_NAME = "DEMO — sintētiska koka karkasa māja (2. posms; nav reāls projekts)"


def demo_frame_project():
    """Koka karkasa demonstrācija (2. posms; saglabāta universālā koda testiem)."""
    p = empty_project(DEMO_FRAME_NAME, "frame")
    p["modules"] = [
        {"name": "Modulis A", "length_mm": 12000, "width_mm": 4000, "confirmed": True, "axes": "822.5 1150"},
        {"name": "Modulis B", "length_mm": 8000, "width_mm": 4000, "confirmed": True, "axes": ""},
    ]
    p["module_fp"] = {str(i): module_fp(m) for i, m in enumerate(p["modules"])}
    p["floor_net_m2"] = 72.0
    p["ceiling_m2"] = 72.0
    p["terraces"] = [{"name": "Priekšējā terase", "area_m2": 12.0}]
    p["wall_height_mm"] = 2700
    p["ext_walls"] = [{"name": "Fasāde N", "length_m": 20.0, "height_mm": None},
                      {"name": "Fasāde S", "length_m": 20.0, "height_mm": None},
                      {"name": "Gals A", "length_m": 4.0, "height_mm": None},
                      {"name": "Gals B", "length_m": 4.0, "height_mm": None}]
    p["int_walls"] = [{"name": "Starpsiena 1", "length_m": 4.0, "height_mm": None},
                      {"name": "Starpsiena 2", "length_m": 3.0, "height_mm": None},
                      {"name": "Starpsiena 3", "length_m": 2.5, "height_mm": None}]
    p["openings"] = [
        {"kind": "Logs", "name": "L1", "width_mm": 1200, "height_mm": 1500, "count": 6, "wall": "Ārsiena"},
        {"kind": "Durvis", "name": "D1 ārdurvis", "width_mm": 1000, "height_mm": 2100, "count": 1, "wall": "Ārsiena"},
        {"kind": "Durvis", "name": "D2 iekšdurvis", "width_mm": 800, "height_mm": 2100, "count": 3, "wall": "Iekšsiena"},
    ]
    p["frames"] = {"ext": {"b_mm": 45, "h_mm": 145, "step_mm": 600}, "int": {"b_mm": 45, "h_mm": 70, "step_mm": 600},
                   "roof": {"b_mm": 45, "h_mm": 195, "step_mm": 600}}
    p["roof"] = {"mode": "slope", "area_m2": None, "footprint_m2": 120.0, "angle_deg": 20.0, "slope_confirmed": True}
    thickness = {(G_EXT, "Karkasa pildījums (vate)"): 145, (G_INT, "Karkasa pildījums (vate)"): 70,
                 (G_ROOF, "Jumta siltinājums"): 200}
    steps = {(G_EXT, "Fasādes latojums"): 600, (G_ROOF, "Latojums"): 350}
    layers = default_layers("frame")
    for layer in layers:
        key = (layer["group"], layer["name"])
        if key in thickness:
            layer["thickness_mm"] = thickness[key]
        if key in steps:
            layer["step_mm"] = steps[key]
        if layer["group"] in (G_FLOOR, G_EXT, G_INT, G_ROOF, G_FINISH) and not layer["source"]:
            layer["source"] = "DEMO pieņēmums"
    p["layers"] = layers
    p["manual"] = [{"group": "Manuālās rindas", "material": "Vannasistabas hidroizolācija (komplekts)", "qty": 1, "unit": "kompl.",
                    "waste_pct": 0, "source": "Manuāli (neautomatizēts apjoms)"}]
    p["prices"] = {}
    return p


def demo_project():
    """Pilna CLT moduļu mājas SINTĒTISKA demonstrācija. Visi biezumi, normas, daudzumi, artikuli un cenas ir izdomāti DEMO dati —
    NAV MLK specifikācijas, normas vai cenas. Ģeometrija: kā karkasa demonstrācijai (2 moduļi, ārsienas 48 m)."""
    p = demo_frame_project()
    p["name"], p["construction"] = DEMO_NAME, "clt"
    p["frames"] = {k: {"b_mm": None, "h_mm": None, "step_mm": None} for k in ("ext", "int", "roof")}
    p["floor_frame_enabled"] = True                      # esošais koka pamatrāmis (rāmja kodols) saglabāts
    demo = "DEMO sintētisks (nav MLK dati)"
    p["clt"] = {
        "ext": {"enabled": True, "thickness_mm": 100, "thickness_confirmed": True, "price_unit": "m³", "waste_pct": 10.0,
                "article": "DEMO-CLT-100", "source": demo},
        "int": {"enabled": True, "thickness_mm": 80, "thickness_confirmed": True, "price_unit": "m²", "waste_pct": 10.0,
                "article": "DEMO-CLT-80", "source": demo},
        "roof": {"enabled": True, "thickness_mm": 120, "thickness_confirmed": False, "price_unit": "m³", "waste_pct": 10.0,
                 "article": None, "source": demo},
        "floor": {"enabled": False, "thickness_mm": None, "thickness_confirmed": False, "price_unit": "m²", "waste_pct": 10.0,
                  "article": None, "source": ""}}
    thickness = {"Ārsienu siltinājums (pie CLT)": 150, "Instalāciju slānis": 50, "Jumta siltinājums": 200}
    steps = {"Fasādes latojums": 600, "Latojums": 350}
    layers = default_layers("clt")
    for layer in layers:
        layer["thickness_mm"] = thickness.get(layer["name"], layer["thickness_mm"])
        layer["step_mm"] = steps.get(layer["name"], layer["step_mm"])
        layer["source"] = layer["source"] or demo
    p["layers"] = layers
    p["catalog"] = [
        {"article": "DEMO-CLT-100", "name": "CLT panelis 100 mm", "spec": "DEMO", "unit": "m³", "unit_price": None, "pack_size": None,
         "source": demo},
        {"article": "DEMO-SKR-6x80", "name": "Skrūve 6×80 (DEMO)", "spec": "DEMO; nav MLK specifikācija", "unit": "gab.",
         "unit_price": 0.12, "pack_size": 200, "source": demo},
    ]
    def rec(group, name, driver, norm=None, qty=None, unit="gab.", art=None, spec="", module="", pack=None, source=demo, waste=None):
        return {"group": group, "article": art, "name": name, "spec": spec, "unit": unit, "driver": driver, "norm": norm, "qty": qty,
                "waste_pct": waste, "pack_size": pack, "module": module, "stage": "", "approved": False, "source": source, "enabled": True}
    p["recipes"] = [
        rec(G_FASTEN, "Skrūves CLT stiprināšanai", "ext_net", 6.0, art="DEMO-SKR-6x80", unit="gab."),
        rec(G_FASTEN, "Hermetizācijas lente savienojumiem", "ext_len", 3.0, unit="m", spec="DEMO"),
        rec(G_FASTEN, "Leņķskavas (DEMO)", "modules", 40.0, unit="gab."),
        rec(G_VENT, "Ventilācijas caurule Ø125 (DEMO)", "direct", qty=36.0, unit="m", spec="DEMO; nav projektēts"),
        rec(G_VENT, "Ventilācijas reste (DEMO)", "direct", qty=8, unit="gab."),
        rec(G_ELEC, "Elektrokabelis 3×2,5 (DEMO)", "floor_net", 2.5, unit="m", spec="DEMO; norma uz m² grīdas"),
        rec(G_ELEC, "Slēdži un kontaktligzdas (DEMO)", "direct", qty=42, unit="gab.", waste=0),
        rec(G_PLUMB, "Ūdensvada caurule (DEMO)", "direct", qty=40.0, unit="m"),
        rec(G_PLUMB, "Kanalizācijas caurule (DEMO)", "direct", qty=18.0, unit="m"),
        rec(G_SANIT, "Sanitārtehnikas komplekts (DEMO)", "direct", qty=1, unit="kompl.", waste=0),
        rec(G_EQUIP, "Rekuperators (DEMO; modelis nav izvēlēts)", "direct", qty=1, unit="gab.", spec="nav norādīta", waste=0),
    ]
    p["manual"] = [{"group": "Manuālās rindas", "material": "Vannasistabas hidroizolācija (komplekts)", "qty": 1, "unit": "kompl.",
                    "waste_pct": 0, "source": "Manuāli (neautomatizēts apjoms)", "article": None, "spec": "", "module": "Modulis A",
                    "stage": "", "pack_size": None, "approved": False}]
    p["other_costs"] = [{"name": n, "amount_eur": None} for n in ("MEP darbs un montāža", "Transports", "Montāža objektā",
                                                                 "Pieskaitāmās izmaksas", "Atlīdzība/peļņa")]
    p["review"] = {"reviewer": "", "confirmed": False}
    return p
