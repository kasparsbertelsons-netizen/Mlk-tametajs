"""Sintētiska materiālu recepšu, cenu un normstundu bibliotēka (Issue #20). Visi dati ir IZDOMĀTI — NAV MLK standarti, cenas vai normas.

    python -m tools.synthetic_library --out samples/library

Satur: katalogu ar cenu derīgumu (viena beigusies, viena nākotnē, viena bez cenas), receptes (ģeometriskas formulas, vienu vēsturisku koeficientu,
vienu neapstiprinātu), normstundas pa operāciju un draiveri, un AD komplektus (virtuve, sanitārtehnika, logi/durvis) ar līmeņiem «standarta»/«augstāks».
"""
import argparse
import pathlib

from src.building_estimate import G_ELEC, G_EQUIP, G_EXT, G_FASTEN, G_FURN, G_INT, G_OPEN, G_PLUMB, G_ROOF, G_SANIT, G_VENT
from src.library import ST_APPROVED, ST_HISTORICAL, ST_UNAPPROVED, export_library, K_FORMULA, K_HISTORICAL

SRC = "SINTĒTISKS (nav MLK dati)"
PSRC = "sintētisks cenrādis"


def _cat(article, name, unit, price, valid_from="2026-01-01", valid_to=None, pack=None):
    return {"article": article, "name": name + " (SINT.)", "spec": "sintētisks", "unit": unit, "unit_price": price, "pack_size": pack,
            "supplier": "Sintētisks piegādātājs", "price_valid_from": valid_from, "price_valid_to": valid_to, "price_source": PSRC if price is not None else ""}


def _recipe(code, group, name, article, unit, driver, norm, *, status=ST_APPROVED, kind=K_FORMULA, qty=None, assumption="", waste=None):
    return {"code": code, "group": group, "name": name, "article": article, "unit": unit, "driver": driver, "norm": norm, "qty": qty, "waste_pct": waste,
            "status": status, "kind": kind, "source": SRC, "assumption": assumption}


def _labour(code, group, name, driver, norm_h, unit, stage="Apdare un montāža", status=ST_APPROVED, kind=K_FORMULA):
    return {"code": code, "group": group, "name": name, "stage": stage, "driver": driver, "unit": unit, "norm_h": norm_h, "status": status, "kind": kind,
            "source": SRC}


def _kit(code, group, name, assumption, positions, covers=()):
    return {"code": code, "group": group, "name": name, "levels": ["standarta", "augstāks"], "default_level": "standarta", "assumption": assumption,
            "covers": list(covers), "positions": positions}


def _pos(code, name, unit, std, high, *, qty=1, driver="direct", norm=None, opening=None):
    return {"code": code, "name": name, "unit": unit, "qty": qty if driver == "direct" else None, "driver": driver, "norm": norm,
            "options": {"standarta": std, "augstāks": high}, "opening": opening}


def build_library():
    catalog = [
        _cat("SINT-LENTE", "Hermetizācijas lente", "m", 1.8), _cat("SINT-LENSKAVA", "Leņķskava", "gab.", 1.5),
        _cat("SINT-EL-NORMA", "Elektroinstalācijas materiāli (EUR/m²)", "m²", 36.0),
        _cat("SINT-HIDRO", "Mitrās telpas hidroizolācija", "kompl.", 210.0),
        _cat("SINT-JLOGA-NOTEC", "Jumta loga apdare un noteces", "kompl.", 85.0),
        _cat("SINT-VENT-KOMPL", "Ventilācijas komplekts", "kompl.", 3100.0),
        _cat("SINT-VIRT-STD", "Virtuves iekārta, standarta (EUR/m)", "m", 520.0), _cat("SINT-VIRT-AUGST", "Virtuves iekārta, augstāka (EUR/m)", "m", 780.0),
        _cat("SINT-PLITS-STD", "Plīts virsma, standarta", "gab.", 380.0), _cat("SINT-PLITS-AUGST", "Plīts virsma, augstāka", "gab.", 690.0),
        _cat("SINT-SINK-STD", "Virtuves jaucējkrāns, standarta", "gab.", 95.0), _cat("SINT-SINK-AUGST", "Virtuves jaucējkrāns, augstāks", "gab.", 210.0),
        _cat("SINT-WC-STD", "Tualetes pods, standarta", "gab.", 160.0), _cat("SINT-WC-AUGST", "Tualetes pods, augstāks", "gab.", 340.0),
        _cat("SINT-DUSA-STD", "Dušas komplekts, standarta", "gab.", 290.0), _cat("SINT-DUSA-AUGST", "Dušas komplekts, augstāks", "gab.", 640.0),
        _cat("SINT-LOGS-STD", "Logs 1200×1500, standarta", "gab.", 230.0), _cat("SINT-LOGS-AUGST", "Logs 1200×1500, augstāks", "gab.", 410.0),
        _cat("SINT-JLOGS-STD", "Jumta logs 780×1400, standarta", "gab.", 370.0), _cat("SINT-JLOGS-AUGST", "Jumta logs 780×1400, augstāks", "gab.", 560.0),
        _cat("SINT-ARDURVIS-STD", "Ārdurvis 1000×2100, standarta", "gab.", 400.0), _cat("SINT-ARDURVIS-AUGST", "Ārdurvis 1000×2100, augstākas", "gab.", 780.0),
        _cat("SINT-VECA-CENA", "Materiāls ar novecojušu cenu", "gab.", 99.0, valid_from="2024-01-01", valid_to="2025-12-31"),
        _cat("SINT-NAKOTNE", "Materiāls ar nākotnes cenu", "gab.", 77.0, valid_from="2099-01-01"),
        _cat("SINT-BEZ-CENAS", "Materiāls bez cenas", "gab.", None),
    ]
    recipes = [
        _recipe("R-LENTE", G_FASTEN, "Hermetizācijas lente savienojumiem", "SINT-LENTE", "m", "ext_len", 3.0, assumption="sintētiska norma: m uz m ārsienu garuma"),
        _recipe("R-LENSKAVA", G_FASTEN, "Leņķskavas", "SINT-LENSKAVA", "gab.", "modules", 40.0, assumption="sintētiska norma: gab. uz moduli"),
        _recipe("R-EL", G_ELEC, "Elektroinstalācijas materiāli (budžeta norma)", "SINT-EL-NORMA", "m²", "floor_net", 1.0, assumption="sintētiska budžeta norma uz m² neto grīdas"),
        _recipe("R-HIDRO", G_PLUMB, "Mitrās telpas hidroizolācija", "SINT-HIDRO", "kompl.", "rooms_wet", 1.0, assumption="viens komplekts uz mitro telpu"),
        _recipe("R-JLOGA-NOTECE", G_ROOF, "Jumta logu apdare un noteces", "SINT-JLOGA-NOTEC", "kompl.", "roof_win", 1.0, assumption="viens komplekts uz jumta logu"),
        _recipe("R-VENT", G_VENT, "Ventilācijas sistēma (AD budžeta komplekts)", "SINT-VENT-KOMPL", "kompl.", "direct", None, qty=1.0, kind="komplekta budžets",
                assumption="sintētisks: rekuperācija visai ēkai; detalizācija PD stadijā"),
        _recipe("R-NEAPST", G_FASTEN, "Papildu stiprinājumi (neapstiprināta norma)", "SINT-LENSKAVA", "gab.", "int_len", 2.0, status=ST_UNAPPROVED,
                assumption="sintētiska neapstiprināta norma"),
        _recipe("R-VESTURE", G_EXT, "Fasādes apdares patēriņš (vēsturisks koeficients)", None, "m²", "ext_net", 1.07, status=ST_HISTORICAL, kind=K_HISTORICAL,
                assumption="sintētisks vēsturisks koeficients no iepriekšēja projekta — nav validēts"),
    ]
    labour = [
        _labour("L-LOGI", G_OPEN, "Fasādes logu un durvju montāža", "facade_win", 1.5, "gab."),
        _labour("L-JLOGI", G_OPEN, "Jumta logu montāža", "roof_win", 2.5, "gab."),
        _labour("L-VIRTUVE", G_FURN, "Virtuves montāža", "kitchen_len", 3.0, "m"),
        _labour("L-FASADE", G_EXT, "Fasādes darbi", "ext_net", 0.6, "m²", stage="Apdare un montāža"),
        _labour("L-SANIT", G_SANIT, "Sanitārtehnikas montāža", "rooms_wet", 14.0, "gab."),
        _labour("L-VESTURE", G_EXT, "Siena: vēsturiskās stundas", "ext_net", 0.9, "m²", stage="Ražošana", status=ST_HISTORICAL, kind=K_HISTORICAL),
    ]
    kits = [
        _kit("K-VIRTUVE", G_FURN, "Virtuves komplekts", "sintētisks: tipveida virtuve ar tehniku; modelis nav izvēlēts", [
            _pos("iekarta", "Virtuves iekārta (pēc garuma)", "m", "SINT-VIRT-STD", "SINT-VIRT-AUGST", driver="kitchen_len", norm=1.0),
            _pos("plits", "Plīts virsma", "gab.", "SINT-PLITS-STD", "SINT-PLITS-AUGST"),
            _pos("jaucejkrans", "Jaucējkrāns", "gab.", "SINT-SINK-STD", "SINT-SINK-AUGST")], covers=["virtuve"]),
        _kit("K-SANIT", G_SANIT, "Sanitārtehnikas komplekts", "sintētisks: komplekts uz mitro telpu", [
            _pos("wc", "Tualetes pods", "gab.", "SINT-WC-STD", "SINT-WC-AUGST", driver="rooms_wet", norm=1.0),
            _pos("dusa", "Dušas komplekts", "gab.", "SINT-DUSA-STD", "SINT-DUSA-AUGST", driver="rooms_wet", norm=1.0)], covers=["sanitārtehnik"]),
        _kit("K-LOGI", G_OPEN, "Logu un durvju komplekts", "sintētisks: standarta izmēri; konkrēts modelis tiek precizēts PD stadijā", [
            _pos("logi", "Fasādes logi", "gab.", "SINT-LOGS-STD", "SINT-LOGS-AUGST", driver="facade_win", norm=1.0, opening="facade_win"),
            _pos("jlogi", "Jumta logi", "gab.", "SINT-JLOGS-STD", "SINT-JLOGS-AUGST", driver="roof_win", norm=1.0, opening="roof_win"),
            _pos("ardurvis", "Ārdurvis", "gab.", "SINT-ARDURVIS-STD", "SINT-ARDURVIS-AUGST", qty=1, opening="door")]),
    ]
    return {"meta": {"name": "Sintētiskā bibliotēka (DEMO)", "version": "1", "synthetic": True,
                     "description": "Izdomāti dati testiem un demonstrācijai; NAV MLK standarti, cenas vai normas."},
            "catalog": catalog, "recipes": recipes, "labour": labour, "kits": kits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="samples/library")
    out = pathlib.Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "biblioteka_sintetiska.json").write_bytes(export_library(build_library()))
    print(f"Ierakstīts: {out / 'biblioteka_sintetiska.json'}")


if __name__ == "__main__":
    main()
