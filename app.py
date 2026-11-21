import streamlit as st
from src.pdf_reader import read_pdf
from src.estimate import Wall, calculate_wall

st.set_page_config(page_title="MLK Tāmēšanas Aģents", page_icon="🏠", layout="wide")
st.title("MLK Tāmēšanas Aģents")
st.caption("1. posms — rāmja norāžu nolasīšana no PDF")

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
            st.warning("Šie ir PDF teksta fragmenti, nevis gatava materiālu tāme. Pārbaudi tos rasējumā. Siju skaitu, šķērsgriezumus un garumus programma vēl nenosaka.")
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
