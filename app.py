import streamlit as st
from src.estimate import Wall, calculate_wall

st.set_page_config(page_title="MLK Tāmēšanas Aģents", page_icon="🏠", layout="wide")
st.title("MLK Tāmēšanas Aģents")
st.info("Pirmā demonstrācija: manuāli ievadīta sienas ģeometrija. PDF analīze un cenas vēl nav ieviestas.")

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
            col1, col2, col3 = st.columns(3)
            col1.metric("Neto sienas laukums", f"{result['net_area_m2']} m²")
            col2.metric("Aptuvenais statņu skaits", str(result["estimated_studs_pcs"]))
            col3.metric("Aptuvenais izolācijas tilpums", f"{result['approx_insulation_m3']} m³")
            st.warning("Aptuvens aprēķins: nav iekļauti stūri, pārsedzes, aiļu pastiprinājumi un statņu aizņemtais izolācijas tilpums.")
        except ValueError as error:
            st.error(str(error))
