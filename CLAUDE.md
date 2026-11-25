# CLAUDE.md — MLK Tāmēšanas Aģents

## Lomas
- **ChatGPT** — projekta arhitekts, uzdevumu sagatavotājs un kvalitātes kontrolieris.
- **Claude** — programmētājs.
- Sadarbība notiek caur kopīgu GitHub repozitoriju (Issues, branches, Pull Requests).

## Sadarbības noteikumi
1. Pirms darba sākšanas sinhronizē aktuālo GitHub versiju (`git fetch origin` un sāc no aktuālā `main`).
2. Izlasi GitHub Issues un projekta dokumentāciju (`README.md`, `docs/`).
3. Izpildi tikai konkrēto apstiprināto uzdevumu. Ārpus tā pamanītās problēmas apraksti PR vai Issue, nelabo pats.
4. Nemaini iepriekš apstiprināto biznesa loģiku (aprēķinu noteikumus, receptes, pieņēmumus) bez saskaņošanas.
5. Katram uzdevumam izveido atsevišķu Git branch. Ja sesijai jau ir piešķirts konkrēts branch, izmanto to.
6. Pēc izstrādes izpildi testus: `python -m unittest discover -s tests`.
7. Publicē izmaiņas GitHub un izveido Pull Request uz `main`.
8. Pull Request aprakstā norādi: izmaiņas, testu rezultātus (ar faktisko izvadi) un neatrisinātās problēmas.
9. Sagaidi ChatGPT pārbaudi un nepieciešamības gadījumā veic labojumus tajā pašā branch.
10. Bez apstiprinājuma neapvieno izmaiņas ar `main` branch.

## Komunikācija ar ChatGPT (pastāvīga kārtība)
- **Pirms katra darba** izlasi jaunākos ChatGPT komentārus attiecīgajā GitHub Issue un ņem tos vērā.
- **Pēc katra uzdevuma** obligāti pievieno komentāru attiecīgajā GitHub Issue ar virsrakstu **`CLAUDE → CHATGPT`**. Komentārā norādi:
  1. Uzdevuma statusu.
  2. Kas ir izdarīts.
  3. Kuri faili ir mainīti.
  4. Testu faktiskos rezultātus (izvade).
  5. Konstatētās problēmas.
  6. Jautājumus ChatGPT.
  7. Ieteicamos nākamos soļus.
  8. Branch nosaukumu un Pull Request saiti.
- Iepriekšējos komentārus **nedzēs un nepārraksti**: jāsaglabājas pilnai sadarbības vēsturei. Labojumus vai papildinājumus raksti kā jaunu komentāru.

## Drošība (repozitorijs ir publisks)
- **Neievietot** GitHub konfidenciālus ražošanas rasējumus, klientu PDF, MLK reālās cenas, persondatus, paroles vai piekļuves atslēgas.
- Testos izmanto tikai sintētiskus datus vai no rasējumiem pārrakstītus nekonfidenciālus fragmentus.

## Projekta noteikumi
- Lietotāja saskarne un dokumentācija — latviešu valodā.
- Aprēķinu drošības noteikumi ir `docs/FRAME_PHASE_1.md`: PDF nolasītos izmērus nejaukt ar pieņēmumiem, neizdomāt neredzamus elementus, nedrošus izmērus rādīt apstiprināšanai.
- Palaišana: `pip install -r requirements.txt` un `streamlit run app.py`.
