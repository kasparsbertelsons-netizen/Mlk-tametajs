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
    st.info("Programma piedāvā rasējumā atrastos izmērus, bet pirms aprēķina tie jāapstiprina. Automātiska sienu un sanmezglu atpazīšana vēl nav ieviesta.")
    suggestions = []
    if ad_pdf is not None:
        if ad_pdf.size > 30 * 1024 * 1024:
            st.error("Maksimālais PDF izmērs ir 30 MB.")
            st.stop()
        try:
            with fitz.open(stream=ad_pdf.getvalue(), filetype="pdf") as document:
                for page in document:
                    page_text = page.get_text("text", sort=True)
                    # Candidate dimensions only: drawing text can contain room, window and detail sizes.
                    for match in re.finditer(r"(?<!\\d)([3-9]\\d{3}|1\\d{4})(?:\\s*[x×]\\s*([3-9]\\d{3}|1\\d{4}))?(?!\\d)", page_text):
                        for value in match.groups():
                            if value:
                                suggestions.append(int(value))
            st.success(f"PDF nolasīts. Atrasti {len(suggestions)} izmēru kandidāti (tie vēl nav apstiprināti moduļa izmēri).")
            if suggestions:
                st.caption("Rasējumā atrastie iespējamie izmēri, mm: " + ", ".join(str(v) for v in sorted(set(suggestions))[:30]))
        except Exception as exc:
            st.error(f"PDF nolasīšanas kļūda: {exc}")
            st.stop()
    st.markdown("**Apstiprini moduļa ārējos izmērus**")
    col1, col2 = st.columns(2)
    with col1:
        length = st.number_input("Moduļa ārējais garums (mm)", min_value=1000, max_value=30000, value=9600, step=100)
    with col2:
        width = st.number_input("Moduļa ārējais platums (mm)", min_value=1000, max_value=10000, value=3500, step=100)
    st.caption("Sānu sijas: 200 × 240 mm. Gala un šķērssijas ievietotas starp sānu sijām, tādēļ to aprēķina garums = ārējais platums − 400 mm.")
    spacing = st.number_input("Regulāro šķērssiju solis (mm)", min_value=300, max_value=1200, value=600, step=50)
    col3, col4 = st.columns(2)
    with col3:
        reinforced = st.number_input("Pastiprinātās 150 × 240 mm šķērssijas (gab.)", min_value=0, max_value=100, value=0, help="Ievadi pēc sienu plāna. Nav automātiski noteikts no PDF.")
    with col4:
        local_extra = st.number_input("Īsie papildstiprinājumi 45 × 240 mm (gab.)", min_value=0, max_value=100, value=0, help="Šajā prototipā bez zināma garuma tie netiek iekļauti kubatūrā.")
    confirmed = st.checkbox("Esmu pārbaudījis moduļa izmērus un izvēlētos pastiprinājumus", key="ad_confirm")
    if st.button("Aprēķināt siju tabulu", type="primary", disabled=not confirmed):
        clear_span = width - 400
        if clear_span <= 0:
            st.error("Moduļa platumam jābūt lielākam par 400 mm.")
        else:
            # Uniform spacing is an estimating assumption, not a verified structural layout.
            interior_positions = max(0, math.ceil(length / spacing) - 1)
            regular = max(0, interior_positions - reinforced)
            items = [
                ("Garās perimetra sijas", 200, 240, length, 2),
                ("Gala sijas starp perimetra sijām", 200, 240, clear_span, 2),
                ("Pastiprinātās šķērssijas (ievadītas)", 150, 240, clear_span, reinforced),
                ("Regulārās šķērssijas (provizoriski)", 45, 240, clear_span, regular),
            ]
            records = [{"Elements": name, "Platums (mm)": w, "Augstums (mm)": h, "Garums (mm)": l, "Gabali": n, "Tilpums (m³)": round(w*h*l*n/1e9, 6)} for name,w,h,l,n in items]
            st.subheader("Provizoriskā siju specifikācija")
            st.dataframe(records, hide_index=True, use_container_width=True)
            a,b,c = st.columns(3)
            a.metric("Pozīcijas", sum(x["Gabali"]>0 for x in records))
            b.metric("Pilna garuma sijas", sum(x["Gabali"] for x in records))
            c.metric("Tilpums bez īsajiem stiprinājumiem", f'{sum(x["Tilpums (m³)"] for x in records):.3f} m³')
            st.warning(f"Īsie lokālie pastiprinājumi: {local_extra} gab. — garumi nav zināmi, tāpēc nav ieskaitīti tilpumā. Regulāro siju skaits ir ģeometrisks pieņēmums; faktiskās balstu un CLT sienu vietas jāpārbauda.")
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            writer.writerow(list(records[0].keys()))
            for item in records:
                writer.writerow(list(item.values()))
            st.download_button("Lejupielādēt provizorisko siju tabulu (CSV Excel)", "\ufeff"+output.getvalue(), file_name="MLK_AD_provizoriskas_sijas.csv", mime="text/csv")
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
