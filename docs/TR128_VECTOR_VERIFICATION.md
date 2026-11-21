# TR-128 grafiskās atpazīšanas pārbaude

Pārbaudīts ar lokāli pieejamo konfidenciālo **TR-128_PD_2026_10_13.pdf**, lapa 2 (PD-01-01). PDF nav augšupielādēts GitHub.

- No rasējuma vektoru ģeometrijas (zelta krāsas aizpildīti taisnstūri, 1:40 mērogs): **25 siju kandidāti**.
- No PDF kokmateriālu specifikācijas: **9 pozīcijas, 25 sijas**.
- Grafika pret tabulu, pie pielaidēm platumam 3 mm un garumam 8 mm: **25/25 sakritības**, 0 neatbilstošu.
- Kokmateriālu tilpums, izmantojot **specifikācijas** augstumu 240 mm: **2,0491908 m³**.

## Ierobežojumi
Šis tests izmanto TR-128 rasējuma specifisko krāsu un PDF vektoru grafiku. Tas vēl **nav universāls jebkuru PDF rasējumu lasītājs**. Ja rasējums ir skenēts attēls, citas krāsas, cits mērogs vai sijas ir saliktas no vairākām figūrām, atpazīšana var neizdoties. Augstums 240 mm nav nolasāms no 2D siju kontūrām; tas ir ņemts no specifikācijas. Šī nav konstruktora apstiprināta tāme.

## Lietotāja pārbaude
Atver TR-128 PD-01-01 un salīdzini ar lietotnē atpazīto elementu sarakstu. Nākamais darbs — vairāku rasējumu/mērogu atbalsts un droša tiešsaistes izvietošana ar Python serveri. GitHub Pages nevar izpildīt Streamlit/PyMuPDF servera kodu.
