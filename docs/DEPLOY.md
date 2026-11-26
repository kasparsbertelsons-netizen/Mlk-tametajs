# MLK tāmētājs — izvietošana telefonam

Programma ir Python/Streamlit; **GitHub Pages nevar palaist PDF analīzi**.

1. Atver https://share.streamlit.io/ un pieslēdzies ar GitHub.
2. Spied **Create app** / **Deploy an app** → **Yup, I have an app**.
3. Izvēlies repozitoriju `kasparsbertelsons-netizen/Mlk-tametajs`, branch `main`, entrypoint `app.py`.
4. Izvēlies privātu lietotnes piekļuvi, ja piedāvāta, un izvieto.
5. Atver Streamlit piešķirto adresi telefonā un augšupielādē TR-128 PD PDF.
6. Pārbaudi: 9 rindas, 25 līmsijas, 2.049191 m³; grafiskie kandidāti 25 un 25 sakritības.

**Datu aizsardzība:** privāts GitHub repozitorijs pats par sevi **nenozīmē privātu Streamlit mājaslapu**. Pirms klienta rasējumu augšupielādes pārbaudi lietotnes piekļuves iestatījumus. Ja nav iespējams ierobežot piekļuvi, neaugšupielādē konfidenciālus failus. Lietotnes kodā pašlaik nav individuālas autentifikācijas.

**Pilnas ēkas tāme (Issue #14):** publiski izvietotajā lietotnē izmantojiet TIKAI sintētisku DEMO projektu un DEMO šablonus. Reālus MLK cenu failus, normas un projektus (arī saglabātos JSON) izmantojiet tikai lokālajā versijā uz `127.0.0.1` (`docs/LOCAL_WINDOWS.md`). Izvietošanai vajadzīga atkarība `openpyxl` (iekļauta `requirements.txt`).

## AD-first sākumskats un izvietotās versijas pārbaude (Issue #18)

**Sākumskats.** Aplikācija atveras režīmā **«Pilnas ēkas AD tāme»**: AD PDF augšupielāde un poga **«Ielādēt AD demonstrāciju (sintētisks AD PDF)»** ir redzamas uzreiz, bez izvēlnēm. Zem augšupielādes ir statusa panelis ar nākamo darbību (*Gaida AD PDF* → *Notiek PDF analīze…* → *atrasti N kandidāti* / *kļūda* / *nekas neatpazīts*). Vecie režīmi saglabāti: **«Vecais AD: tikai grīdas rāmis»** un **«PD: līmsiju specifikācija»**.

**Kā atšķirt vecu izvietojumu no jaunā.** Lapas augšā zem nosaukuma ir rinda `Versija <izlaiduma versija> · commit <īsais SHA>`.
- Izlaiduma versija ir `RELEASE_VERSION` failā `src/app_shell.py` (jāatjaunina katram izlaidumam).
- Īsais commit SHA tiek nolasīts no vides mainīgajiem (`MLK_COMMIT`, `GIT_COMMIT`, `COMMIT_SHA`, `SOURCE_VERSION`, `RENDER_GIT_COMMIT`, `GITHUB_SHA`) vai no `git rev-parse`. Ja nekas nav pieejams (piem., izvietojums bez `.git`), rinda rāda `commit nav pieejams` un jāpaļaujas uz izlaiduma versiju. Streamlit Community Cloud commit SHA lietotnei automātiski NEPADOD — tāpēc izlaiduma versija ir galvenais identifikators.
- Ja lapā versijas rindas nav vai tā ir cita, tā ir veca izvietojuma kopija: Streamlit lietotnē izvēlies **Reboot app** vai pārbaudi, ka izvietojuma branch ir `main` ar jaunāko merge.

**Izvietošanas konfigurācijas pārskats (repozitorijā pieejamais).** `requirements.txt` (streamlit ≥1.67 <2, PyMuPDF, openpyxl), `.streamlit/config.toml` (maxUploadSize 30 MB, XSRF ieslēgts, gatherUsageStats izslēgts, tumša tēma), entrypoint `app.py`. Citu izvietošanas failu (Dockerfile, Procfile, workflow) nav. Konfigurācija nav mainīta.

**Ko NEESAM pārbaudījuši.** Publiski izvietotā Streamlit lietotne netika atvērta vai testēta; mobilās pārbaudes veiktas lokāli (`tools/e2e_mobile_default_flow.js`, Playwright iPhone 13 emulācija pret `streamlit run app.py`). Pēc izvietošanas pārbaudi versijas rindu un to pašu plūsmu telefonā.
