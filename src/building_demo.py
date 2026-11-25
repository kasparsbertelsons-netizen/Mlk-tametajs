"""Sintētisks demonstrācijas projekts (Issue #12). Visi skaitļi ir izdomāti; nav MLK dati, cenas vai reāli rasējumi.

Ēka: divi taisnstūra moduļi 12000×4000 un 8000×4000, novietoti galu pie gala (kopīgā šuve 4000 mm gar abām malām —
fasādē NETIEK skaitīta). Ārsienu garums = 2×(20+4) = 48 m, nevis moduļu perimetru summa 56 m.
Karkasa šķērsgriezumi, soļi, biezumi un cenas ir DEMONSTRĀCIJAS vērtības, nevis MLK receptes.
"""
from src.building_estimate import (
    G_EXT, G_FINISH, G_FLOOR, G_INT, G_ROOF, default_layers, empty_project, module_fp,
)

DEMO_NAME = "DEMO — sintētiska divu moduļu māja (nav reāls projekts)"


def demo_project():
    p = empty_project(DEMO_NAME)
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
    layers = default_layers()
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
