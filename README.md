# MLK Tāmēšanas Aģents

Moduļu māju tāmēšanas programmas sākuma versija. **Demonstrācija, nevis pilna būvniecības tāme.**

## Palaišana

```bash
pip install -r requirements.txt
streamlit run app.py
```

Testi: `python -m unittest discover -s tests`.

### Testēšanas vide
Testēts ar **Python 3.13**, **Streamlit 1.67.0** un **PyMuPDF 1.28.2** (`requirements.txt` zemākās versijas ir šīs). Saskarnes testi izmanto Streamlit `AppTest` ar failu augšupielādi (`FileUploader.upload`) un `import pymupdf`; ja vide neatbilst, tie **krīt**, nevis tiek klusi izlaisti (`TestEnvironment`). Testos izmanto tikai sintētiskus PDF.

## Lokāla palaišana Windows 11
Lietotni var palaist **tikai uz sava datora** (adrese `127.0.0.1`, bez telemetrijas, PDF netiek sūtīti uz internetu):
1. Instalējiet **Python 3.11 vai jaunāku** no python.org (atzīmējiet "py launcher").
2. Repozitorija mapē divreiz noklikšķiniet **`start_mlk_windows.bat`** (pirmajā reizē tas izveido `.venv` un instalē `requirements.txt`; internets vajadzīgs tikai tam).
3. Atveriet **http://127.0.0.1:8501** (parasti atveras pats).

Detaļas, problēmu risināšana un **kas faktiski testēts** (Windows `.bat` šajā izstrādes vidē nav izpildīts): `docs/LOCAL_WINDOWS.md`.

## Diagnostika reāliem AD rasējumiem (lokāli)
`diagnostika_windows.bat` (vai `python -m tools.ad_diagnostics FAILS.pdf --page 3 --control 12000x4000`) parāda lapas, vektoru skaitu, kontūru/izmēru kandidātus, mērogu un neveiksmes iemeslus, un salīdzina ar **jūsu** zināmiem izmēriem. Plāna lapu var norādīt pats. Brīvprātīgs **sanitizēts kopsavilkums** (tikai skaitļi un kodi, bez nosaukumiem, teksta, koordinātām un izmēriem) tiek izdrukāts apskatei; rīks neko nesūta. 3–5 soļu instrukcija un atļauto lauku saraksts: `docs/REAL_AD_VALIDATION.md`. Sintētisks tests nav reālo rasējumu validācija.

## Kas ir gatavs
AD režīms: provizoriska moduļa **grīdas pamatrāmja** (bez pastiprinājumiem) aprēķins no lietotāja apstiprinātiem L un W; skat. `docs/FLOOR_FRAME_CORE.md`. PD režīms nolasa siju specifikācijas tabulu. **AD vektoru prototips** (kandidāti no PDF vektoriem ar pierādījumiem un priekšskatījumu; `docs/AD_VECTOR_PROTOTYPE.md`) un sintētiski paraugi praktiskai pārbaudei: `samples/ad_vector/README.md`.

Manuāli apstiprinātas sienas ģeometrijas aprēķins: neto laukums, aptuvens statņu skaits, aptuvens izolācijas tilpums. PDF analīze, cenas, Excel eksports, lietotāju autentifikācija un publiska tīmekļa adrese vēl nav izveidota.

## Drošība
Šis repozitorijs ir publisks. **Neievietot** klientu rasējumus, MLK reālās cenas, paroles vai persondatus.

## Tālāk
PDF ģeometrijas nolasīšana ar izmēru apstiprināšanu, karkasa/SIP/CLT receptes, privātas cenas un darba normas, Excel tāme, klienta piedāvājums, droša izvietošana internetā.
