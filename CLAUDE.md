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

## Drošība (repozitorijs ir publisks)
- **Neievietot** GitHub konfidenciālus ražošanas rasējumus, klientu PDF, MLK reālās cenas, persondatus, paroles vai piekļuves atslēgas.
- Testos izmanto tikai sintētiskus datus vai no rasējumiem pārrakstītus nekonfidenciālus fragmentus.

## Projekta noteikumi
- Lietotāja saskarne un dokumentācija — latviešu valodā.
- Aprēķinu drošības noteikumi ir `docs/FRAME_PHASE_1.md`: PDF nolasītos izmērus nejaukt ar pieņēmumiem, neizdomāt neredzamus elementus, nedrošus izmērus rādīt apstiprināšanai.
- Palaišana: `pip install -r requirements.txt` un `streamlit run app.py`.
