"""Lokāls diagnostikas rīks reāliem AD rasējumiem (Issue #8).

    python -m tools.ad_diagnostics FAILS.pdf [--page 3] [--control 12000x4000] [--html pārskats.html]
                                              [--summary-out kopsavilkums.json | --print-summary]
    python -m tools.ad_diagnostics --allowed-fields

    python -m tools.ad_diagnostics --interactive [FAILS.pdf]    (rīks pats jautā: PDF, lapas, kontrolizmērus, saglabāšanu)

Viss notiek LOKĀLI uz šī datora: rīks neizmanto tīklu, neko nesūta un nepublicē. Pēc noklusējuma tas tikai
izdrukā pārskatu konsolē un NEVIENU failu neveido; HTML pārskats un sanitizētais kopsavilkums tiek saglabāti
tikai pēc skaidra pieprasījuma. Pilns pārskats satur PDF saturu (nekopīgot); sanitizētais kopsavilkums satur
tikai atļauto lauku sarakstu (`--allowed-fields`) un ir jāapskata pirms jebkādas kopīgošanas.
"""
import argparse
import base64
import datetime
import html
import json
import os
import pathlib
import re
import sys

from src import ad_diagnostics as diag
from src.ad_vector import render_preview_png

MAX_PDF_BYTES = 300 * 1024 * 1024
BANNER = ("LOKĀLS PĀRSKATS: satur PDF saturu (teksta fragmentus, izmērus, koordinātas). Nekopīgot, nepublicēt, "
          "neievietot GitHub. Kopīgošanai paredzēts tikai sanitizētais kopsavilkums.")
TEXT_CLASS_LV = {"floor": "grīdas plāns", "roof": "jumta plāns", "list": "titullapa/saraksts", "other": "cits"}
PAGE_STATUS_LV = {"ok": "analizēta", "no_vector_geometry": "nav vektoru ģeometrijas", "error": "analīzes kļūda"}
CATEGORY_LV = {"match": "sakrīt (≤ 0,5 %)", "small": "neliela novirze (≤ 2 %)", "medium": "vidēja novirze (≤ 10 %)",
               "large": "liela novirze (> 10 %)", "no_candidate": "nav nolasīta kandidāta"}


# --- atskaišu mapes: PDF saturs nedrīkst nonākt sinhronizētās mapēs -------------------------------------------
REPORTS_FOLDER_NAME = "MLK_diagnostika"
SYNC_RE = re.compile(r"^(onedrive|dropbox|google ?drive|icloud|pcloud|nextcloud|owncloud|sharepoint|(mega|box|sync)\b)", re.I)
SYNC_ENV_VARS = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")


def default_reports_dir(environ=None):
    """Noklusētā atskaišu mape ārpus lietotāja sinhronizētajām mapēm (Windows: %LOCALAPPDATA%)."""
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if base:
        return pathlib.Path(base) / REPORTS_FOLDER_NAME
    data_home = environ.get("XDG_DATA_HOME")
    return (pathlib.Path(data_home) if data_home else pathlib.Path.home() / ".local" / "share") / REPORTS_FOLDER_NAME


def is_synced_folder(path, environ=None):
    """Heiristika: ceļš šķiet OneDrive / Dropbox / Google Drive / iCloud u. c. sinhronizētā mapē."""
    environ = os.environ if environ is None else environ
    resolved = pathlib.Path(path).expanduser().resolve(strict=False)
    if any(SYNC_RE.match(part) for part in resolved.parts):
        return True
    for name in SYNC_ENV_VARS:
        root = environ.get(name)
        if root:
            try:
                resolved.relative_to(pathlib.Path(root).resolve(strict=False))
                return True
            except ValueError:
                pass
    return False


def unique_path(directory, stem, suffix):
    """Brīvs faila nosaukums: esošs fails netiek pārrakstīts (pievieno -1, -2 …)."""
    directory = pathlib.Path(directory)
    candidate = directory / f"{stem}{suffix}"
    number = 0
    while candidate.exists():
        number += 1
        candidate = directory / f"{stem}-{number}{suffix}"
    return candidate


# --- pārskata saturs (kopīgs tekstam un HTML) -------------------------------------------------------------
def scale_lines(analysis):
    scale = analysis.get("scale")
    if not scale:
        return ["Mērogs: nav noteikts (lapa nav analizēta)."]
    declared = scale["declared"]
    if declared["status"] == "viens":
        lines = [f"Mērogs lapā norādīts: 1:{declared['denominator']} (teksts '{declared['sources'][0]['text']}')."]
    elif declared["status"] == "vairāki":
        lines = ["Mērogs lapā: norādīti VAIRĀKI dažādi mērogi: " +
                 ", ".join(f"1:{n}" for n in sorted({s['denominator'] for s in declared['sources']})) + "."]
    else:
        lines = ["Mērogs lapā NAV norādīts."]
    if scale["dimension_implied"]:
        lines.append("No izmēru norādēm izsecinātais mērogs (nolasīts): " +
                     ", ".join(f"{d['dimension']}: 1:{d['denominator']}" for d in scale["dimension_implied"]) + ".")
    return lines


def failure_reasons(analysis):
    """Cilvēkam lasāmi neveiksmes iemesli lapai un kandidātiem (lokālam pārskatam)."""
    reasons = []
    if analysis["status"] != "ok":
        reasons.extend(analysis.get("notes", []))
    elif not analysis["candidates"]:
        unmeasured = sum(1 for e in analysis["excluded"] if e["kind"] == "unmeasured")
        reasons.append("Nav neviena kontūras kandidāta: nav kontūru, kurām piesaistītas izmēru norādes "
                       f"(kontūras bez izmēru norādēm: {unmeasured}; atrastās izmēru norādes: "
                       f"{len(analysis['dimensions'])}).")
    return reasons


def page_rows(report):
    rows = []
    for page in report["pages"]:
        v = page["vectors"] or {}
        rows.append([
            page["page"], TEXT_CLASS_LV.get(page["text_class"], page["text_class"]), page["text_chars"],
            v.get("drawing_paths", "-"), f"{v.get('contour_rectangle', '-')}/{v.get('contour_polygon', '-')}",
            f"{v.get('segment_horizontal', '-')}/{v.get('segment_vertical', '-')}",
            f"{v.get('segment_diagonal', '-')}/{v.get('curve', '-')}", v.get("images", "-"),
            page["rotation"], "*" if page["page"] in report["analyses"] else ""])
    return rows


PAGE_HEADER = ["Lapa", "Klasifikators", "Teksta zīmes", "Vektoru ceļi", "Kontūras (taisnst./citas)",
               "Nogriežņi (H/V)", "Diag./līknes", "Attēli", "Rotācija", "Analizēta"]


def candidate_value(cand):
    return f"{cand['length_mm']}×{cand['width_mm']} mm" if cand["transferable"] else "L/W netiek piedāvāti"


# --- teksta pārskats ------------------------------------------------------------------------------------
def _table(header, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    line = lambda cells: "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))
    return "\n".join([line(header), line(["-" * w for w in widths])] + [line(r) for r in rows])


def render_text(report):
    out = ["=" * 100, BANNER, "=" * 100]
    inp = report["input"]
    out.append(f"Fails: {inp['file_name']} | izmērs: {inp['size_bytes'] / 1e6:.2f} MB | lapas: {inp['pages_total']} | "
               f"izveidots: {report['generated_at']}")
    out.append(f"Ievades statuss: {inp['status']}")
    if inp["status"] != "ok":
        out.append({"invalid_pdf": "Fails nav atpazīts kā PDF.", "encrypted": "PDF ir aizsargāts ar paroli: nav atbalstīts.",
                    "too_many_pages": f"PDF pārsniedz {diag.MAX_PAGES} lapu limitu.",
                    "unreadable": "PDF neizdevās atvērt."}.get(inp["status"], ""))
        return "\n".join(out)
    out += ["", "--- LAPAS (NOLASĪTS NO PDF) ---", _table(PAGE_HEADER, page_rows(report)),
            "(* = lapa analizēta; klasifikators ir tikai teksta heiristika, vektoru skaitļi ir skaitļi no PDF)"]
    sel = report["selection"]
    out += ["", f"--- LAPU IZVĒLE: režīms '{sel['mode']}', analizētās lapas: {sel['pages'] or 'nav'} ---"]
    if sel["invalid_pages"]:
        out.append(f"Nederīgi lapu numuri (ārpus 1–{inp['pages_total']}): {sel['invalid_pages']}")
    out += sel["notes"]
    for number, analysis in sorted(report["analyses"].items()):
        out += ["", f"--- ANALĪZE, {number}. LAPA (NOLASĪTS NO PDF, automātiski): {PAGE_STATUS_LV.get(analysis['status'])} ---"]
        out += scale_lines(analysis)
        for dim in analysis.get("dimensions", []):
            out.append(f"  izmēru norāde {dim['id']}: {dim['value_mm']} mm ({'horizontāla' if dim['orientation'] == 'H' else 'vertikāla'}, "
                       f"izmērītais garums {dim['measured_pt']} pt)")
        for reason in failure_reasons(analysis):
            out.append(f"  NEVEICĀS/NEPIETIEK: {reason}")
        for cand in analysis["candidates"]:
            out.append(f"  kandidāts {cand['id']}: {cand['status']}, {candidate_value(cand)}, "
                       f"iemeslu kodi: {', '.join(cand['reason_codes']) or '-'}")
            out += [f"      problēma: {issue}" for issue in cand["issues"]]
        for item in analysis["excluded"]:
            if item["kind"] not in ("page_frame", "unmeasured"):
                out.append(f"  izslēgts ({item['kind']}): {item['reason']}")
        unmeasured = sum(1 for e in analysis["excluded"] if e["kind"] == "unmeasured")
        if unmeasured:
            out.append(f"  kontūras bez piesaistītām izmēru norādēm (nav kandidāti): {unmeasured}")
    out += ["", "--- LIETOTĀJA KONTROLIZMĒRI (ievadīti ar --control; NAV nolasīti no PDF) ---"]
    out += [f"  {i}. {c['length_mm']}×{c['width_mm']} mm" for i, c in enumerate(report["controls"], 1)] or ["  nav norādīti"]
    out += ["", "--- SALĪDZINĀJUMS: nolasītais pret lietotāja kontroli ---"]
    for entry in report["comparison"]["entries"]:
        c = entry["control"]
        if entry["candidate"]:
            k = entry["candidate"]
            out.append(f"  kontrole {entry['control_index']} ({c['length_mm']}×{c['width_mm']}) ↔ {entry['candidate_id']} "
                       f"({k['length_mm']}×{k['width_mm']}, {k['status']}): novirze L {entry['deviation_mm']['length']:+d} mm, "
                       f"W {entry['deviation_mm']['width']:+d} mm ({entry['deviation_pct']} %): {CATEGORY_LV[entry['category']]}")
        else:
            out.append(f"  kontrole {entry['control_index']} ({c['length_mm']}×{c['width_mm']}): {CATEGORY_LV['no_candidate']}")
    if report["comparison"]["candidates_without_control"]:
        out.append("  nolasītie kandidāti bez kontrolizmēra: " + ", ".join(report["comparison"]["candidates_without_control"]))
    out += ["", "Atgādinājums: pamatrāmis neietver 150×240 pastiprinājumus un 45×240 īsās starpsijas; ja kas nav droši nolasīts, "
            "nekas netiek izdomāts. Kandidāta statuss nepierāda konstrukcijas robežu."]
    return "\n".join(out)


# --- HTML pārskats ------------------------------------------------------------------------------------
def _e(value):
    return html.escape(str(value), quote=True)


def _html_table(header, rows):
    head = "".join(f"<th>{_e(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def render_html(report, previews=None):
    """Pašpietiekams HTML (CSP: bez skriptiem un tīkla; viss saturs ekranēts)."""
    previews = previews or {}
    inp = report["input"]
    parts = [
        "<!doctype html><html lang='lv'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\">"
        "<title>Lokāls AD diagnostikas pārskats</title><style>"
        "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;max-width:1200px}"
        "table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #bbb;padding:4px 8px;font-size:13px}"
        "th{background:#eee}.warn{background:#b00020;color:#fff;padding:10px;font-weight:bold}"
        ".read{border-left:6px solid #1565c0;padding-left:10px;margin:14px 0}"
        ".ctrl{border-left:6px solid #6a1b9a;padding-left:10px;margin:14px 0}"
        ".tag{font-size:11px;font-weight:bold;padding:1px 6px;color:#fff}"
        ".tag.r{background:#1565c0}.tag.c{background:#6a1b9a}img{max-width:100%;border:1px solid #999}"
        "</style></head><body>",
        f"<div class='warn'>{_e(BANNER)}</div>",
        "<h1>Lokāls AD diagnostikas pārskats</h1>",
        f"<p>Fails: <b>{_e(inp['file_name'])}</b> · izmērs {inp['size_bytes'] / 1e6:.2f} MB · lapas {_e(inp['pages_total'])}"
        f" · izveidots {_e(report['generated_at'])} · ievades statuss <b>{_e(inp['status'])}</b></p>"]
    if inp["status"] != "ok":
        parts.append("<p>PDF netika atvērts; skat. statusu.</p></body></html>")
        return "".join(parts)
    parts.append("<div class='read'><span class='tag r'>NOLASĪTS NO PDF</span><h2>Lapas</h2>"
                 + _html_table(PAGE_HEADER, page_rows(report))
                 + "<p>Klasifikators ir tikai teksta heiristika; vektoru skaitļi ir skaitļi no PDF. "
                   "Analizētās lapas ir atzīmētas ar *.</p></div>")
    sel = report["selection"]
    parts.append(f"<p><b>Lapu izvēle:</b> režīms {_e(sel['mode'])}, analizētās lapas {_e(sel['pages'] or 'nav')}.</p>")
    for note in sel["notes"]:
        parts.append(f"<p>{_e(note)}</p>")
    if sel["invalid_pages"]:
        parts.append(f"<p>Nederīgi lapu numuri: {_e(sel['invalid_pages'])}</p>")
    for number, analysis in sorted(report["analyses"].items()):
        parts.append(f"<div class='read'><span class='tag r'>NOLASĪTS NO PDF (automātiski)</span>"
                     f"<h2>{_e(number)}. lapa: {_e(PAGE_STATUS_LV.get(analysis['status']))}</h2>")
        parts += [f"<p>{_e(line)}</p>" for line in scale_lines(analysis)]
        if analysis.get("dimensions"):
            parts.append(_html_table(["Norāde", "Virziens", "Vērtība (mm)", "Izmērītais garums (pt)"],
                                     [[d["id"], d["orientation"], d["value_mm"], d["measured_pt"]] for d in analysis["dimensions"]]))
        parts += [f"<p><b>Neveicās / nepietiek:</b> {_e(r)}</p>" for r in failure_reasons(analysis)]
        for cand in analysis["candidates"]:
            parts.append(f"<h3>{_e(cand['id'])}: {_e(cand['status'])}, {_e(candidate_value(cand))}</h3>"
                         f"<p>Iemeslu kodi: {_e(', '.join(cand['reason_codes']) or '-')}</p>")
            parts.append("<details><summary>Pierādījumi un problēmas</summary><ul>"
                         + "".join(f"<li>{_e(x)}</li>" for x in cand["evidence"])
                         + "".join(f"<li><b>⚠</b> {_e(x)}</li>" for x in cand["issues"])
                         + f"</ul><p><i>{_e(cand['disclaimer'])}</i></p></details>")
        for item in analysis["excluded"]:
            if item["kind"] not in ("page_frame", "unmeasured"):
                parts.append(f"<p>Izslēgts ({_e(item['kind'])}): {_e(item['reason'])}</p>")
        if number in previews:
            parts.append("<img alt='Lapas priekšskatījums' src='data:image/png;base64,"
                         + base64.b64encode(previews[number]).decode("ascii") + "'>")
        parts.append("</div>")
    parts.append("<div class='ctrl'><span class='tag c'>LIETOTĀJA KONTROLIZMĒRI (nav nolasīti no PDF)</span><h2>Kontrolizmēri</h2>")
    parts.append(_html_table(["#", "L (mm)", "W (mm)"], [[i, c["length_mm"], c["width_mm"]] for i, c in enumerate(report["controls"], 1)])
                 if report["controls"] else "<p>Nav norādīti.</p>")
    parts.append("</div><h2>Salīdzinājums: nolasītais pret lietotāja kontroli</h2>")
    rows = []
    for e in report["comparison"]["entries"]:
        k, dm = e["candidate"], e["deviation_mm"]
        rows.append([e["control_index"], f"{e['control']['length_mm']}×{e['control']['width_mm']}",
                     e["candidate_id"] or "-", f"{k['length_mm']}×{k['width_mm']}" if k else "-",
                     f"{dm['length']:+d} / {dm['width']:+d}" if dm else "-", f"{e['deviation_pct']} %" if k else "-",
                     CATEGORY_LV[e["category"]]])
    parts.append(_html_table(["Kontrole", "Kontrolizmērs", "Kandidāts", "Nolasīts", "Novirze L/W (mm)", "Novirze", "Kategorija"], rows)
                 if rows else "<p>Nav kontrolizmēru.</p>")
    parts.append("<p>Pamatrāmis neietver 150×240 pastiprinājumus un 45×240 īsās starpsijas. Ja kas nav droši nolasīts, "
                 "nekas netiek izdomāts. Kandidāta statuss nepierāda konstrukcijas robežu.</p></body></html>")
    return "".join(parts)


# --- interaktīvā ievade (validē Python, nekad shell) -------------------------------------------------------------
MAX_TRIES = 5
YES = {"j", "ja", "jā", "y", "yes"}
NO = {"", "n", "ne", "nē", "no"}


def strip_path_input(text):
    """Noņem atstarpes un vienu apkārtējo pēdiņu pāri (Windows 'Copy as path' ielīmē ceļu pēdiņās)."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _ask(prompt, input_fn):
    try:
        return input_fn(prompt)
    except EOFError:
        raise diag.DiagnosticsError("Ievade pārtraukta.") from None


def ask_yes_no(prompt, input_fn=input, say=print):
    """Jā/nē jautājums; noklusējums ir NĒ (Enter). Atkārto, ja atbilde nav saprotama."""
    for _ in range(MAX_TRIES):
        answer = _ask(prompt + " (j/n, Enter = n): ", input_fn).strip().lower()
        if answer in YES:
            return True
        if answer in NO:
            return False
        say("Atbildiet j vai n.")
    raise diag.DiagnosticsError("Netika saņemta saprotama atbilde.")


def interactive_session(pdf_arg=None, *, input_fn=input, say=print, environ=None, now=None):
    """Pieprasa un VALIDĒ visu ievadi (PDF ceļš, lapas, kontrolizmēri, saglabāšana). Atgriež parsētas vērtības;
    nekas netiek veidots kā komandrindas teksts. HTML netiek pārrakstīts: nosaukums vienmēr ir jauns."""
    environ = os.environ if environ is None else environ
    now = now or datetime.datetime.now
    pdf_text = strip_path_input(pdf_arg or "")
    pdf_path = None
    for _ in range(MAX_TRIES):
        if not pdf_text:
            pdf_text = strip_path_input(_ask("PDF faila ceļš (var ielīmēt vai ievilkt failu šajā logā): ", input_fn))
        if not pdf_text or any(ord(c) < 32 for c in pdf_text):
            say("Norādiet PDF faila ceļu.")
            pdf_text = ""
            continue
        candidate = pathlib.Path(pdf_text)
        try:
            ok = candidate.is_file()
        except OSError:
            ok = False
        if ok:
            pdf_path = candidate
            break
        say(f"Fails nav atrasts: {pdf_text}")
        pdf_text = ""
    if pdf_path is None:
        raise diag.DiagnosticsError("PDF fails nav norādīts.")

    pages = None
    for _ in range(MAX_TRIES):
        answer = _ask("Plāna lapa(s), piem. 3 vai 3,5 vai 3-6 (Enter = automātiski): ", input_fn).strip()
        if not answer:
            break
        try:
            pages = diag.parse_page_list(answer)
            break
        except diag.DiagnosticsError as error:
            say(str(error))
    else:
        raise diag.DiagnosticsError("Netika saņemts derīgs lapu numurs.")

    controls = []
    for _ in range(MAX_TRIES * 2):
        answer = _ask(f"Jūsu zināmais moduļa izmērs mm, piem. 12000x4000 (Enter = {'beigt' if controls else 'bez kontroles'}): ",
                      input_fn).strip()
        if not answer:
            break
        try:
            controls.append(diag.parse_control(answer))
        except diag.DiagnosticsError as error:
            say(str(error))

    html_path = None
    reports_dir = default_reports_dir(environ)
    if ask_yes_no(f"Saglabāt lokālu HTML pārskatu (satur PDF saturu) mapē {reports_dir}?", input_fn, say):
        if is_synced_folder(reports_dir, environ):
            say(f"Mape {reports_dir} šķiet sinhronizēta: pārskats netiek saglabāts. Norādiet citu mapi ar "
                "--html (komandrindā).")
        else:
            stamp = now().strftime("%Y%m%d_%H%M%S")
            html_path = unique_path(reports_dir, f"diagnostika_{stamp}", ".html")
    print_summary = ask_yes_no("Parādīt sanitizēto kopsavilkumu apskatei (nekas netiek sūtīts)?", input_fn, say)
    return {"pdf_path": pdf_path, "pages": pages, "controls": controls, "html_path": html_path,
            "print_summary": print_summary}


def _safe_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")      # Windows konsole: nekrītam uz nekodējamām rakstzīmēm
            except Exception:
                pass


# --- komandrinda ------------------------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m tools.ad_diagnostics", description="Lokāla AD rasējumu diagnostika (nekas netiek sūtīts uz internetu).")
    p.add_argument("pdf", nargs="?", help="AD PDF fails (lokāls)")
    p.add_argument("--page", "--pages", action="append", metavar="N", help="analizējamā lapa(s): 3 vai 3,5 vai 3-6 "
                   "(lietojiet, ja automātiskais klasifikators plāna lapu neatrod)")
    p.add_argument("--all-pages", action="store_true", help="analizēt visas lapas")
    p.add_argument("--control", action="append", metavar="LxW", help="JŪSU zināmais moduļa izmērs mm, piem. 12000x4000 "
                   "(var atkārtot; netiek nolasīts no PDF)")
    p.add_argument("--html", metavar="FAILS", help="saglabāt lokālu HTML pārskatu (satur PDF saturu!)")
    p.add_argument("--no-preview", action="store_true", help="HTML pārskatā neiekļaut lapu attēlus")
    p.add_argument("--summary-out", metavar="FAILS", help="saglabāt SANITIZĒTO kopsavilkumu JSON failā (brīvprātīgi)")
    p.add_argument("--print-summary", action="store_true", help="izdrukāt sanitizēto kopsavilkumu konsolē apskatei")
    p.add_argument("--allowed-fields", action="store_true", help="parādīt sanitizētā kopsavilkuma atļauto lauku sarakstu")
    p.add_argument("--overwrite", action="store_true", help="atļaut pārrakstīt esošu izvades failu")
    p.add_argument("--allow-synced-folder", action="store_true",
                   help="atļaut saglabāt sinhronizētā mapē (OneDrive/Dropbox u. c.): ATSKAITE SATUR PDF SATURU")
    p.add_argument("--interactive", action="store_true",
                   help="rīks pats pieprasa un validē ievadi (PDF ceļš, lapas, kontrolizmēri, saglabāšana)")
    return p


def _check_output(path_text, pdf_path, overwrite, allow_synced=False, environ=None):
    path = pathlib.Path(path_text)
    resolved = path.resolve()
    if resolved == pdf_path.resolve() or resolved.suffix.lower() == ".pdf":
        raise diag.DiagnosticsError("Izvades fails nedrīkst būt PDF (lai netiktu pārrakstīts rasējums).")
    if not allow_synced and is_synced_folder(resolved.parent, environ):
        raise diag.DiagnosticsError(
            f"Mape '{resolved.parent}' šķiet sinhronizēta (OneDrive/Dropbox/Google Drive u. c.): atskaite ar PDF saturu "
            f"varētu nonākt mākonī. Izvēlieties mapi ārpus sinhronizācijas (piem., {default_reports_dir(environ)}) vai "
            "skaidri atļaujiet ar --allow-synced-folder.")
    if resolved.exists() and not overwrite:
        raise diag.DiagnosticsError(f"Fails jau pastāv: {path}. Lietojiet --overwrite vai citu nosaukumu.")
    return path


def main(argv=None, out=None, input_fn=input, environ=None):
    if out is None:
        _safe_console()
    out = out or sys.stdout
    say = lambda text="": print(text, file=out)
    args = build_parser().parse_args(argv)
    if args.allowed_fields:
        say(diag.describe_allowed_fields())
        return 0
    environ = os.environ if environ is None else environ
    try:
        if args.pdf == "":                      # .bat nodod "" (tukšs arguments), ja fails nav ievilkts
            args.pdf = None
        if args.interactive:
            if any((args.page, args.all_pages, args.control, args.html, args.summary_out, args.print_summary, args.overwrite)):
                raise diag.DiagnosticsError("Interaktīvajā režīmā norādiet tikai PDF (ja vēlaties); pārējo rīks pajautās pats.")
            options = interactive_session(args.pdf, input_fn=input_fn, say=say, environ=environ)
            pdf_path, pages, controls = options["pdf_path"], options["pages"], options["controls"]
            html_path, summary_path, print_summary = options["html_path"], None, options["print_summary"]
            overwrite = False
        else:
            if not args.pdf:
                raise diag.DiagnosticsError("Norādiet PDF failu. Piemērs: python -m tools.ad_diagnostics fails.pdf --page 3")
            pdf_path = pathlib.Path(args.pdf)
            if not pdf_path.is_file():
                raise diag.DiagnosticsError(f"Fails nav atrasts: {pdf_path}")
            pages = sorted({n for part in args.page or [] for n in diag.parse_page_list(part)}) or None
            controls = [diag.parse_control(text) for text in args.control or []]
            overwrite, print_summary = args.overwrite, args.print_summary
            html_path = (_check_output(args.html, pdf_path, overwrite, args.allow_synced_folder, environ)
                         if args.html else None)
            summary_path = (_check_output(args.summary_out, pdf_path, overwrite, args.allow_synced_folder, environ)
                            if args.summary_out else None)
        if pdf_path.stat().st_size > MAX_PDF_BYTES:
            raise diag.DiagnosticsError("PDF ir pārāk liels (> 300 MB).")
        if html_path and summary_path and html_path.resolve() == summary_path.resolve():
            raise diag.DiagnosticsError("HTML pārskatam un kopsavilkumam jābūt dažādiem failiem.")
    except diag.DiagnosticsError as error:
        say(f"KĻŪDA: {error}")
        return 2
    except KeyboardInterrupt:
        say("Pārtraukts.")
        return 2

    data = pdf_path.read_bytes()
    report = diag.run_diagnostics(data, pages=pages, all_pages=bool(getattr(args, "all_pages", False)), controls=controls,
                                  file_name=pdf_path.name)
    say(render_text(report))

    if html_path:
        previews = {}
        if not args.no_preview:
            for number, analysis in report["analyses"].items():
                if analysis["status"] == "ok":
                    try:
                        previews[number] = render_preview_png(data, analysis, None)
                    except Exception:
                        pass
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(report, previews), encoding="utf-8")
        say(f"\nHTML pārskats saglabāts LOKĀLI: {html_path} (satur PDF saturu: nekopīgot).")
    if summary_path or print_summary:
        summary = diag.build_sanitized_summary(report)
        text = diag.summary_json(summary)
        say("\n=== SANITIZĒTAIS KOPSAVILKUMS (apskatiet pirms kopīgošanas; rīks to nekur nesūta) ===")
        say(text)
        say("Satur tikai skaitļus un fiksētus kodus. Atļauto lauku saraksts: --allowed-fields.")
        if summary_path:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(text + "\n", encoding="utf-8")
            say(f"Kopsavilkums saglabāts LOKĀLI: {summary_path} (nekas netiek sūtīts automātiski).")
    return 0 if report["input"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
