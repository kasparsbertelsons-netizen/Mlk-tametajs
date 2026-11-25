"""Sintētisks demonstrācijas projekts (Issue #12). Visi skaitļi ir izdomāti; nav MLK dati, cenas vai reāli rasējumi.

Ēka: divi taisnstūra moduļi 12000×4000 un 8000×4000, novietoti galu pie gala (kopīgā šuve 4000 mm gar abām malām —
fasādē NETIEK skaitīta). Ārsienu garums = 2×(20+4) = 48 m, nevis moduļu perimetru summa 56 m.
Karkasa šķērsgriezumi, soļi, biezumi un cenas ir DEMONSTRĀCIJAS vērtības, nevis MLK receptes.
"""
from src.building_estimate import (
    G_ELEC, G_EQUIP, G_EXT, G_FASTEN, G_FINISH, G_FLOOR, G_INT, G_OPEN, G_PLUMB, G_ROOF, G_SANIT, G_VENT, default_layers, empty_project,
    module_fp, set_price,
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


# --- SINTĒTISKAS DEMO cenas un darba normas (nav MLK dati!) ---------------------------------------------------------------
DEMO_SUPPLIER = "DEMO piegādātājs"
DEMO_RATE_EUR_H = 32.0                         # pilna darba pašizmaksas likme (DEMO)
DEMO_OVERHEAD_PCT, DEMO_MARKUP_PCT, DEMO_VAT_PCT = 8.0, 15.0, 21.0
DEMO_OTHER_COSTS = [("Ārpakalpojums: ģeodēziskā uzmērīšana", "Ārpakalpojumi", 650.0), ("Transports", "Transports", 1850.0),
                    ("Montāža objektā", "Montāža", 5400.0)]
# artikuls → (nosaukums, vienība, cena EUR bez PVN, iepakojums)
DEMO_CATALOG = {
    "DEMO-CLT-100": ("CLT panelis 100 mm", "m³", 520.0, None), "DEMO-CLT-80": ("CLT panelis 80 mm", "m²", 38.0, None),
    "DEMO-CLT-120": ("CLT panelis 120 mm", "m³", 540.0, None),
    "DEMO-LOGS": ("Logs 1200×1500", "gab.", 240.0, None), "DEMO-DURV-ARD": ("Ārdurvis 1000×2100", "gab.", 410.0, None),
    "DEMO-DURV-IEK": ("Iekšdurvis 800×2100", "gab.", 95.0, None), "DEMO-TERASE": ("Terases segums", "m²", 42.0, None),
    "DEMO-GRIDA-APD": ("Grīdas apdare", "m²", 21.0, None), "DEMO-FAS-APD": ("Fasādes apdare", "m²", 34.0, None),
    "DEMO-FAS-LAT": ("Fasādes latojums", "m", 1.4, None), "DEMO-VEJA": ("Vēja membrāna", "m²", 2.1, None),
    "DEMO-SILT-EXT": ("Ārsienu siltinājums", "m³", 95.0, None), "DEMO-INSTAL": ("Instalāciju slānis", "m³", 88.0, None),
    "DEMO-IEKS-APD": ("Iekšējā apdare (ārsienas)", "m²", 12.5, None), "DEMO-INT-APD": ("Iekšsienu apdare", "m²", 11.5, None),
    "DEMO-SILT-JUMTS": ("Jumta siltinājums", "m³", 92.0, None), "DEMO-MEMBR": ("Jumta membrāna", "m²", 2.6, None),
    "DEMO-J-LAT": ("Jumta latojums", "m", 1.2, None), "DEMO-SEGUMS": ("Jumta segums", "m²", 29.0, None),
    "DEMO-GRIESTI": ("Griestu apdare", "m²", 13.0, None), "DEMO-SKR-6x80": ("Skrūve 6×80", "gab.", 0.12, 200),
    "DEMO-LENTE": ("Hermetizācijas lente", "m", 1.9, None), "DEMO-LENSKAVA": ("Leņķskava", "gab.", 1.6, None),
    "DEMO-VENT-D125": ("Ventilācijas caurule Ø125", "m", 6.8, None), "DEMO-RESTE": ("Ventilācijas reste", "gab.", 7.5, None),
    "DEMO-KABELIS": ("Elektrokabelis 3×2,5", "m", 1.1, None), "DEMO-SLEDZI": ("Slēdzis/kontaktligzda", "gab.", 4.2, None),
    "DEMO-UDENS": ("Ūdensvada caurule", "m", 2.9, None), "DEMO-KANAL": ("Kanalizācijas caurule", "m", 3.6, None),
    "DEMO-SANIT": ("Sanitārtehnikas komplekts", "kompl.", 1650.0, None), "DEMO-REKUP": ("Rekuperators", "gab.", 2400.0, None),
    "DEMO-HIDRO": ("Vannasistabas hidroizolācija", "kompl.", 380.0, None),
}
DEMO_FLOOR_FRAME_EUR_M3, DEMO_PIR_EUR_M2 = 420.0, 18.5
# darba operācijas: (grupa, nosaukums, pamats, normstundas uz vienību, tiešas stundas, vienība)
DEMO_OPERATIONS = [
    (G_FLOOR, "Grīdas rāmja izgatavošana", "floor_frame", 0.60, None, "m²"),
    (G_EXT, "CLT ārsienu montāža un apstrāde", "ext_net", 0.50, None, "m²"),
    (G_EXT, "Fasādes apdares ražošana", "ext_net", 0.30, None, "m²"),
    (G_INT, "CLT iekšsienu montāža", "int_one", 0.40, None, "m²"),
    (G_INT, "Iekšsienu apdare", "int_both", 0.35, None, "m²"),
    (G_ROOF, "Jumta paneļu un seguma montāža", "roof", 0.45, None, "m²"),
    (G_OPEN, "Logu montāža", "win", 1.5, None, "gab."),
    (G_OPEN, "Durvju montāža", "door", 2.0, None, "gab."),
    (G_FINISH, "Griestu apdare", "ceiling", 0.25, None, "m²"),
    (G_FASTEN, "Stiprinājumu un hermetizācijas darbi", "ext_len", 0.10, None, "m"),
    (G_VENT, "Ventilācijas montāža", "direct", None, 24.0, "h"),
    (G_ELEC, "Elektroinstalācija", "direct", None, 60.0, "h"),
    (G_PLUMB, "Ūdens un kanalizācijas montāža", "direct", None, 40.0, "h"),
    (G_SANIT, "Sanitārtehnikas montāža", "direct", None, 16.0, "h"),
    (G_EQUIP, "Iekārtu uzstādīšana", "direct", None, 12.0, "h"),
]


def demo_project():
    """Pilna CLT moduļu mājas SINTĒTISKA, PILNĪBĀ CENOTA demonstrācija (materiāli, darbs, izmaksas, pārdošanas cena).
    Visi biezumi, normas, artikuli, cenas, likmes un procenti ir izdomāti DEMO dati — NAV MLK specifikācijas, normas vai cenas.
    Ģeometrija: 2 moduļi (12000×4000 ar pastiprinājumiem, 8000×4000), ārsienas 48 m, iekšsienas 9,5 m."""
    p = demo_frame_project()
    p["name"], p["construction"], p["is_demo"] = DEMO_NAME, "clt", True
    p["frames"] = {k: {"b_mm": None, "h_mm": None, "step_mm": None} for k in ("ext", "int", "roof")}
    p["floor_frame_enabled"] = True                      # esošais koka pamatrāmis (rāmja kodols) saglabāts
    demo = "DEMO sintētisks (nav MLK dati)"
    p["clt"] = {
        "ext": {"enabled": True, "thickness_mm": 100, "thickness_confirmed": True, "price_unit": "m³", "waste_pct": 10.0,
                "article": "DEMO-CLT-100", "source": demo},
        "int": {"enabled": True, "thickness_mm": 80, "thickness_confirmed": True, "price_unit": "m²", "waste_pct": 10.0,
                "article": "DEMO-CLT-80", "source": demo},
        "roof": {"enabled": True, "thickness_mm": 120, "thickness_confirmed": False, "price_unit": "m³", "waste_pct": 10.0,
                 "article": "DEMO-CLT-120", "source": demo},
        "floor": {"enabled": False, "thickness_mm": None, "thickness_confirmed": False, "price_unit": "m²", "waste_pct": 10.0,
                  "article": None, "source": ""}}
    thickness = {"Ārsienu siltinājums (pie CLT)": 150, "Instalāciju slānis": 50, "Jumta siltinājums": 200}
    steps = {"Fasādes latojums": 600, "Latojums": 350}
    articles = {"Grīdas apdare": "DEMO-GRIDA-APD", "Fasādes apdare": "DEMO-FAS-APD", "Fasādes latojums": "DEMO-FAS-LAT",
                "Vēja membrāna": "DEMO-VEJA", "Ārsienu siltinājums (pie CLT)": "DEMO-SILT-EXT", "Instalāciju slānis": "DEMO-INSTAL",
                "Iekšējā apdare": "DEMO-IEKS-APD", "Iekšsienu apdare abās pusēs": "DEMO-INT-APD", "Jumta siltinājums": "DEMO-SILT-JUMTS",
                "Membrāna": "DEMO-MEMBR", "Latojums": "DEMO-J-LAT", "Jumta segums": "DEMO-SEGUMS", "Griestu apdare": "DEMO-GRIESTI"}
    layers = default_layers("clt")
    for i, layer in enumerate(layers, 1):
        layer["id"] = f"demo-layer-{i}"
        layer["thickness_mm"] = thickness.get(layer["name"], layer["thickness_mm"])
        layer["step_mm"] = steps.get(layer["name"], layer["step_mm"])
        layer["source"] = layer["source"] or demo
        layer["article"] = articles[layer["name"]]
    p["layers"] = layers
    for i, o in enumerate(p["openings"], 1):
        o["id"] = f"demo-opening-{i}"
        o["article"] = {"L1": "DEMO-LOGS", "D1 ārdurvis": "DEMO-DURV-ARD", "D2 iekšdurvis": "DEMO-DURV-IEK"}[o["name"]]
    for i, t in enumerate(p["terraces"], 1):
        t["id"], t["article"] = f"demo-terrace-{i}", "DEMO-TERASE"
    def rec(group, name, driver, norm=None, qty=None, unit="gab.", art=None, spec="", module="", pack=None, source=demo, waste=None):
        return {"group": group, "article": art, "name": name, "spec": spec, "unit": unit, "driver": driver, "norm": norm, "qty": qty,
                "waste_pct": waste, "pack_size": pack, "module": module, "stage": "", "approved": False, "source": source, "enabled": True}
    p["recipes"] = [
        rec(G_FASTEN, "Skrūves CLT stiprināšanai", "ext_net", 6.0, art="DEMO-SKR-6x80", unit="gab."),
        rec(G_FASTEN, "Hermetizācijas lente savienojumiem", "ext_len", 3.0, art="DEMO-LENTE", unit="m", spec="DEMO"),
        rec(G_FASTEN, "Leņķskavas (DEMO)", "modules", 40.0, art="DEMO-LENSKAVA", unit="gab."),
        rec(G_VENT, "Ventilācijas caurule Ø125 (DEMO)", "direct", qty=36.0, art="DEMO-VENT-D125", unit="m", spec="DEMO; nav projektēts"),
        rec(G_VENT, "Ventilācijas reste (DEMO)", "direct", qty=8, art="DEMO-RESTE", unit="gab."),
        rec(G_ELEC, "Elektrokabelis 3×2,5 (DEMO)", "floor_net", 2.5, art="DEMO-KABELIS", unit="m", spec="DEMO; norma uz m² grīdas"),
        rec(G_ELEC, "Slēdži un kontaktligzdas (DEMO)", "direct", qty=42, art="DEMO-SLEDZI", unit="gab."),
        rec(G_PLUMB, "Ūdensvada caurule (DEMO)", "direct", qty=40.0, art="DEMO-UDENS", unit="m"),
        rec(G_PLUMB, "Kanalizācijas caurule (DEMO)", "direct", qty=18.0, art="DEMO-KANAL", unit="m"),
        rec(G_SANIT, "Sanitārtehnikas komplekts (DEMO)", "direct", qty=1, art="DEMO-SANIT", unit="kompl."),
        rec(G_EQUIP, "Rekuperators (DEMO; modelis nav izvēlēts)", "direct", qty=1, art="DEMO-REKUP", unit="gab.", spec="nav norādīta"),
    ]
    for i, r in enumerate(p["recipes"], 1):
        r["id"] = f"demo-recipe-{i}"
    p["manual"] = [{"id": "demo-manual-1", "group": "Manuālās rindas", "material": "Vannasistabas hidroizolācija (komplekts)", "qty": 1,
                    "unit": "kompl.", "waste_pct": 0, "source": "Manuāli (neautomatizēts apjoms)", "article": "DEMO-HIDRO", "spec": "",
                    "module": "Modulis A", "stage": "", "pack_size": None, "approved": False}]
    p["catalog"] = [{"article": art, "name": name + " (DEMO)", "spec": "DEMO", "unit": unit, "unit_price": price, "pack_size": pack,
                     "supplier": DEMO_SUPPLIER, "source": demo} for art, (name, unit, price, pack) in DEMO_CATALOG.items()]
    # automātiskās rindas (rāmja kodols, PIR) tiek cenotas pēc STABILAS rindas identitātes
    p["prices"] = {}
    set_price(p, "floor_frame:modulis a", DEMO_FLOOR_FRAME_EUR_M3, "m³")
    set_price(p, "floor_frame:modulis b", DEMO_FLOOR_FRAME_EUR_M3, "m³")
    set_price(p, "pir", DEMO_PIR_EUR_M2, "m²")
    p["labour"] = {"rate_eur_h": DEMO_RATE_EUR_H, "operations": [
        {"id": f"demo-op-{i}", "group": g, "name": name, "stage": "", "module": "", "driver": drv, "qty": None, "unit": unit,
         "norm_h": norm, "hours": hours, "rate_eur_h": None, "approved": False, "source": demo, "enabled": True}
        for i, (g, name, drv, norm, hours, unit) in enumerate(DEMO_OPERATIONS, 1)]}
    p["other_costs"] = [{"id": f"demo-oc-{i}", "name": n, "category": c, "group": None, "amount_eur": a, "source": demo}
                        for i, (n, c, a) in enumerate(DEMO_OTHER_COSTS, 1)]
    p["pricing"] = {"overhead_pct": DEMO_OVERHEAD_PCT, "method": "markup", "markup_pct": DEMO_MARKUP_PCT, "margin_pct": None,
                    "vat_enabled": True, "vat_pct": DEMO_VAT_PCT}
    p["review"] = {"reviewer": "", "confirmed": False, "fp": None}
    return p
