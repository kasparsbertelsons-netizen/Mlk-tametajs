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

## Kas ir gatavs
AD režīms: provizoriska moduļa **grīdas pamatrāmja** (bez pastiprinājumiem) aprēķins no lietotāja apstiprinātiem L un W; skat. `docs/FLOOR_FRAME_CORE.md`. PD režīms nolasa siju specifikācijas tabulu. **AD vektoru prototips** (kandidāti no PDF vektoriem ar pierādījumiem un priekšskatījumu; `docs/AD_VECTOR_PROTOTYPE.md`) un sintētiski paraugi praktiskai pārbaudei: `samples/ad_vector/README.md`.

Manuāli apstiprinātas sienas ģeometrijas aprēķins: neto laukums, aptuvens statņu skaits, aptuvens izolācijas tilpums. PDF analīze, cenas, Excel eksports, lietotāju autentifikācija un publiska tīmekļa adrese vēl nav izveidota.

## Drošība
Šis repozitorijs ir publisks. **Neievietot** klientu rasējumus, MLK reālās cenas, paroles vai persondatus.

## Tālāk
PDF ģeometrijas nolasīšana ar izmēru apstiprināšanu, karkasa/SIP/CLT receptes, privātas cenas un darba normas, Excel tāme, klienta piedāvājums, droša izvietošana internetā.
