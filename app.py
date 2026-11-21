import streamlit as st
from src.pdf_reader import read_pdf
from src.estimate import Wall, calculate_wall

st.set_page_config(page_title="MLK Tāmēšanas Aģents", page_icon="🏠", layout="wide")
st.title("MLK Tāmēšanas Aģents")
st.caption("1. posms — rāmja norāžu nolasīšana no PDF")

import math
import re
import csv
import io
import fitz

st.subheader("Arhitektūras rasējums → provizoriska grīdas rāmja tāme")
st.caption("Rebel tipa moduļiem. Šis ir cenu piedāvājuma aprēķins, nevis konstruktora projekts.")
mode = st.radio("Aprēķina režīms", ["AD — prognozēt rāmi", "PD — nolasīt specifikāciju"], horizontal=True)

if mode == "AD — prognozēt rāmi":
    ad_pdf = st.file_uploader("Augšupielādē arhitektūras daļas PDF (AD)", type=["pdf"], key="ad_pdf")
    if ad_pdf is not None:
        if ad_pdf.size > 30 * 1024 * 1024:
            st.error("Maksimālais PDF izmērs ir 30 MB.")
            st.stop()
        try:
            with fitz.open(stream=ad_pdf.getvalue(), filetype="pdf") as doc:
                floor_pages = [(i + 1, p.get_text("text", sort=True)) for i, p in enumerate(doc) if re.search(r"\bFloor plan\b", p.get_text("text", sort=True), re.I)]
                roof_pages = [(i + 1, p.get_text("text", sort=True)) for i, p in enumerate(doc) if re.search(r"\bRoof plan\b", p.get_text("text", sort=True), re.I)]
                if not floor_pages:
                    st.error("Nav atrasta atpazīstama grīdas plāna lapa.")
                    st.stop()
                page_no, floor_text = max(floor_pages, key=lambda item: len(item[1]))
                def dimension_candidates(txt):
                    # Standalone millimetre dimensions, excluding decimals, room areas and window sizes.
                    return [int(m.group()) for m in re.finditer(r"(?<![\d.,x×])\d{4,5}(?![\d.,x×])", txt)]
                candidates = dimension_candidates(floor_text)
                roof_candidates = dimension_candidates(max(roof_pages, key=lambda item: len(item[1]))[1]) if roof_pages else []
                # The Rebel module outer length is the largest plausible main floor dimension.
                long_values = [v for v in roof_candidates + candidates if 6000 <= v <= 20000]
                length = max(long_values) if long_values else None
                # For a Rebel module, select the standard outer width found on the floor or roof plan.
                widths = [v for v in roof_candidates + candidates if v in (3500, 4000)]
                width = max(set(widths), key=widths.count) if widths else None
                if not length or not width or length <= width:
                    st.error("No plāna nav droši nosakāmi Rebel moduļa gabarīti. Aprēķins netiek veikts ar izdomātiem izmēriem.")
                    st.stop()
                # Estimate from known Rebel rules, without asking the user for beam dimensions.
                clear_span = width - 400
                spacing = 600
                interior_count = max(0, math.ceil(length / spacing) - 1)
                # Structural reinforcements are NOT inferred as fact from the floor plan.
                rows = [
                    ("Garās perimetra sijas", 200, 240, length, 2, "Rebel standarts"),
                    ("Gala sijas", 200, 240, clear_span, 2, "Rebel standarts"),
                    ("Regulārās šķērssijas", 45, 240, clear_span, interior_count, "600 mm solis, provizoriski"),
                ]
                result = [{"Elements": n, "b (mm)": w, "h (mm)": h, "L (mm)": l, "Gab.": q, "m³": round(w*h*l*q/1e9, 6), "Pamatojums": note} for n,w,h,l,q,note in rows]
                st.success("Arhitektūras rasējums analizēts. Provizoriskā siju tabula sagatavota automātiski.")
                st.subheader("Automātiski noteiktie izmēri")
                x,y,z = st.columns(3)
                x.metric("Moduļa garums", f"{length} mm")
                y.metric("Moduļa platums", f"{width} mm")
                z.metric("Siju solis", "600 mm")
                st.caption(f"Izmēru avots: Floor plan, PDF {page_no}. lapa; platums pārbaudīts pret jumta plānu, ja tas pieejams. Atpazīšana ir provizoriska.")
                st.subheader("Provizoriskā Rebel grīdas rāmja siju tabula")
                st.dataframe(result, hide_index=True, use_container_width=True)
                a,b,c=st.columns(3)
                a.metric("Sijas (gab.)",sum(r["Gab."] for r in result))
                b.metric("Kokmateriāli",f'{sum(r["m³"] for r in result):.3f} m³')
                c.metric("Siju pozīcijas",len(result))
                st.warning("Šī ir sākotnējā cenu tāme, nevis pilna konstrukcijas specifikācija. CLT sienu pastiprinātās sijas, sanmezglu īsie pastiprinājumi un iespējamās nestandarta zonas vēl nav automātiski noteiktas un NAV ieskaitītas tabulā. Tādēļ kopējais apjoms var būt par mazu.")
                out=io.StringIO()
                writer=csv.writer(out,delimiter=";")
                writer.writerow(list(result[0].keys()))
                for row in result:
                    writer.writerow(list(row.values()))
                st.download_button("Lejupielādēt automātisko siju tabulu (CSV Excel)", "\ufeff"+out.getvalue(), file_name="MLK_AD_automatiskas_sijas.csv", mime="text/csv")
        except Exception as exc:
            st.error(f"PDF analīzes kļūda: {exc}")

else:
    pdf = st.file_uploader("Augšupielādē rasējumu PDF", type=["pdf"], help="PDF tiek analizēts šajā sesijā; programma to neievieto GitHub.")
    if pdf:
        if pdf.size > 30 * 1024 * 1024:
            st.error("Maksimālais PDF izmērs ir 30 MB.")
        else:
            try:
                data = read_pdf(pdf.getvalue())
                st.success(f"Nolasītas {len(data['pages'])} lapas.")
                if data["mentions"]:
                    st.subheader("Atrastas konstrukciju norādes")
                    st.dataframe(data["mentions"], hide_index=True, use_container_width=True)
                else:
                    st.warning("Tekstā nav atrastas atpazīstamas GL, koka karkasa vai CLT norādes. Iespējams, rasējums ir attēls.")
    
                from src.frame_schedule import parse_beams, summarize
                beams = parse_beams([page["text"] for page in data["pages"]])
                st.subheader("Grīdas rāmja līmsiju specifikācija")
                if beams:
                    st.dataframe([beam.to_dict() for beam in beams], hide_index=True, use_container_width=True)
                    totals = summarize(beams)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Pozīcijas", totals["positions"])
                    c2.metric("Līmsijas", totals["pieces"])
                    c3.metric("Kokmateriāli", f'{totals["volume_m3"]:.3f} m³')
                    st.caption("Aprēķins no PDF specifikācijas tabulas, bez atgriezumiem. Pārbaudi pret rasējumu.")
                    import csv
                    import io
                    buffer = io.StringIO()
                    writer = csv.writer(buffer, delimiter=";")
                    writer.writerow(["Nr", "Platums_mm", "Augstums_mm", "Garums_mm", "Gabali", "Apjoms_m3", "PDF_lapa"])
                    for beam in beams:
                        writer.writerow([beam.number, beam.width_mm, beam.height_mm, beam.length_mm, beam.count, f"{beam.volume_m3:.6f}", beam.page])
                    st.download_button("Lejupielādēt līmsiju specifikāciju (CSV Excel)", "\ufeff" + buffer.getvalue(), file_name="MLK_limsiju_specifikacija.csv", mime="text/csv")
                else:
                    st.info("Šajā PDF netika atrasta atbalstīta līmsiju specifikācijas tabula.")
                st.subheader("Rāmja sijas no PDF grafikas — eksperimentāls")
                import fitz
                from src.frame_vectors import detect_beams, compare_to_schedule
                with fitz.open(stream=pdf.getvalue(), filetype="pdf") as doc:
                    graphic = []
                    for page_index, page in enumerate(doc):
                        if "Structural Frame" not in data["pages"][page_index]["text"]:
                            continue
                        graphic.extend([{**beam, "page": page_index + 1}
                                        for beam in detect_beams(page, drawing_scale=40)])
                st.caption("Atpazīšana pēc TR-128 zelta krāsas vektoru kontūrām; mērogs 1:40. Citiem projektiem jākalibrē.")
                st.metric("Grafiski atrastie siju kandidāti", len(graphic))
                if graphic:
                    st.dataframe(graphic, hide_index=True, use_container_width=True)
                if graphic and beams:
                    comparison = compare_to_schedule(graphic, beams)
                    st.metric("Ar specifikāciju sakrītošie elementi", len(comparison["matched"]))
                    if comparison["unmatched_graphics"] or comparison["unmatched_schedule"]:
                        st.warning("Daļa elementu nesakrīt ar specifikāciju; nepieciešama pārbaude.")
                    else:
                        st.success("Visi grafiski atpazītie elementi sakrīt ar PDF specifikāciju (pie pielaidēm).")
                st.warning("Augstums 240 mm no 2D grafikas nav nosakāms: to var iegūt tikai no specifikācijas vai konstrukcijas datiem.")
                st.info("Siju skaits, šķērsgriezumi un garumi ir nolasīti no tabulas; grafiskā atpazīšana ir eksperimentāla. Rezultātu pārbaudi pret rasējumu.")
                with st.expander("Pārbaudīt nolasīto tekstu pa lapām"):
                    for page in data["pages"]:
                        st.text_area(f"Lapa {page['page']}", page["text"][:12000], height=140, key=f"page_{page['page']}")
            except (ValueError, RuntimeError, Exception) as error:
                st.error(f"PDF neizdevās analizēt: {error}")
    
with st.expander("Iepriekšējais sienas demonstrācijas kalkulators"):
    with st.form("wall"):
        length = st.number_input("Sienas garums (m)", min_value=0.01, value=6.0)
        height = st.number_input("Sienas augstums (m)", min_value=0.01, value=2.8)
        openings = st.number_input("Ailu kopējais laukums (m²)", min_value=0.0, value=2.0)
        spacing = st.number_input("Statņu solis (m)", min_value=0.01, value=0.5)
        depth = st.number_input("Izolācijas biezums (m)", min_value=0.01, value=0.2)
        confirmed = st.checkbox("Apstiprinu ievadītos izmērus")
        submit = st.form_submit_button("Aprēķināt")
    if submit:
        if not confirmed:
            st.error("Vispirms apstiprini ievadītos izmērus.")
        else:
            try:
                result = calculate_wall(Wall(length, height, openings, spacing, depth))
                st.json(result)
                st.warning("Aptuvens aprēķins; nav konstruktora specifikācija.")
            except ValueError as error:
                st.error(str(error))
