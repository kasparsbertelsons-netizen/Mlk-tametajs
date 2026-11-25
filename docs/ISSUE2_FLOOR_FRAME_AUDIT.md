# Issue #2 — moduļa grīdas rāmja aprēķina audits

**Datums:** 2026-11-25. **Pārbaudītā versija:** `main` @ `ecd3c30`. **Dati:** tikai sintētiski PDF (ģenerēti testā ar PyMuPDF), bez klientu rasējumiem.

## Kas tika pārbaudīts
Grīdas rāmja aprēķins ir tikai **AD režīmā** (`app.py` 19.–79. rinda). Tas nav atsevišķā `src/` modulī, tāpēc testi palaiž `app.py` caur Streamlit `AppTest` un "augšupielādē" sintētisku PDF. **Kods nav mainīts.**

Pašreizējie dokumentētie AD noteikumi (`app.py`):

| Elements | b × h, mm | L | Gab. |
|---|---|---|---|
| Garās perimetra sijas | 200 × 240 | moduļa garums | 2 |
| Gala sijas | 200 × 240 | platums − 400 | 2 |
| Regulārās šķērssijas | 45 × 240 | platums − 400 | ceil(garums / 600) − 1 |

Platums tiek pieņemts tikai, ja tas ir 3500 vai 4000 mm. Garums ir lielākais skaitlis 6000–20000 grīdas **un jumta** plānā.

## Sintētiskais tests: 12000 × 4000 mm (neatkarīgs aprēķins)
- Garās sijas: 2 × 0,2 · 0,24 · 12,0 = **1,152 m³**
- Gala sijas: L = 4000 − 2·200 = 3600; 2 × 0,2 · 0,24 · 3,6 = **0,3456 m³**
- Šķērssijas: asis 600, 1200 … 11400 mm no ārmalas → **19 gab.**; 19 × 0,045 · 0,24 · 3,6 = **0,73872 m³**
- **Kopā: 23 gab., 2,23632 m³** (lietotnē 2.236 m³)

**Faktiskais rezultāts:** lietotne izdod tieši šīs vērtības. Tests `TestADFloorFrameSynthetic` — OK.

### Ass solis pret tīro atstarpi
Kods lieto **ass soli 600 mm** no moduļa ārmalas. Ja 600 mm būtu **tīrā atstarpe** starp sijām: tīrais garums 12000 − 400 = 11600; n·45 + (n+1)·600 ≤ 11600 ⇒ n ≥ 17,05 ⇒ **18 gab.** (−1 gab., −0,03888 m³). Kura interpretācija ir MLK noteikums, **nav dokumentēts** → jāsaskaņo.

## AD un PD ceļi
AD (ģeometrija no "Floor plan"/"Roof plan" teksta) un PD (tabula "Timber Element list") ir **atsevišķi koda ceļi**, kurus izvēlas radio poga; tie nedalās ar datiem. Pārbaudīts: PD tabula AD režīmā → "Nav atrasta atpazīstama grīdas plāna lapa"; AD plāns PD režīmā → "netika atrasta … specifikācijas tabula". Rezultāti netiek sajaukti.

Piezīme: AD ceļš neizmanto `src/pdf_reader.read_pdf`, tāpēc tam nav 100 lapu limita un paroles PDF pārbaudes.

## Konstatētās neatbilstības (fiksētas ar `@expectedFailure`, kods nav mainīts)
1. **Šķērssiju pārklāšanās ar gala siju, ja garums nedalās ar 600.** L = 12100: kods dod 20 gab., pēdējā ass 12000 mm, bet gala sija ir 11900–12100. Jebkurā interpretācijā pareizi būtu ≤ 19. Pārvērtējums: +1 gab., +0,03888 m³ (0,045 · 0,24 · 3,6).
2. **Jumta pārkare maina moduļa garumu.** Grīdas plāns 12000, jumta plāns 12600 → garums 12600. Komentārs kodā saka "main floor dimension", bet `max()` ņem arī jumta skaitļus.
3. **Platumu izvēlas pēc biežuma.** Ja grīdas plānā 3500 (piem., telpas izmērs) parādās biežāk nekā 4000, modulis kļūst 3500 plats.
4. **Grīdas plāna lapu izvēlas pēc garākā teksta.** Ja titullapā/sarakstā ir vārdi "Floor plan" un vairāk teksta nekā plānā, tiek izvēlēta nepareizā lapa. Šajā gadījumā rezultāts ir kļūdas paziņojums, nevis nepareizs skaitlis.

## Reproducējamie ierobežojumi (droši: aprēķins netiek veikts)
- Izmēri ar tūkstošu atdalītāju ("12 000", kā TR-126 dokumentācijā) netiek nolasīti → kļūda, bez izdomātiem izmēriem.
- Platums, kas nav 3500/4000 (piem., 3600) → kļūda.
- Nav "Floor plan" lapas → kļūda.

## Biznesa noteikumi, kas jāsaskaņo (nav mainīti)
- 600 mm: ass solis vai tīrā atstarpe? No kurienes mēra (ārmala, gala sijas ass, iekšmala)?
- Vai šķērssijas ir pilnā 200 mm gala siju iekšpusē (L = platums − 400) — pareizi?
- Vai Rebel platumi ir tikai 3500 un 4000 mm?
- Vai moduļa garums jāņem tikai no grīdas plāna?
- Noapaļošana / zāģēšanas rezerve — šobrīd nav.

## Citas piezīmes
- Streamlit 1.67 brīdina, ka `use_container_width` ir novecojis (paredzēts noņemt pēc 2025-12-31). Pagaidām darbojas.
- Testiem vajag Streamlit ar `AppTest` failu augšupielādi (pārbaudīts ar 1.67.0). Ar vecāku versiju AD testi tiek izlaisti (`skip`), nevis krīt.

## Ieteiktais nākamais solis
Pēc noteikumu saskaņošanas iznest AD grīdas rāmja loģiku atsevišķā `src/` modulī (tīras funkcijas: izmēru nolasīšana un siju aprēķins), salabot neatbilstības 1–4 un noņemt `@expectedFailure`.
