# Issue #2 — moduļa grīdas rāmja aprēķina audits

**Versija:** 2 (atjaunota pēc ChatGPT komentāra Issue #2, 2026-11-25).
**Pārbaudītā versija:** `main` @ `ecd3c30`. **Dati:** tikai sintētiski PDF (ģenerēti testā ar PyMuPDF), bez klientu rasējumiem.
**`app.py` un `src/` nav mainīti.** Šis dokuments un testi fiksē esošo uzvedību un apstiprinātos noteikumus; aprēķina labošana ir atsevišķs uzdevums.

## Svarīgi: kas ir apstiprināts un kas nav
- Esošie testi un 1. versijas skaitļi (23 gab., 2,23632 m³) ir **esošās koda uzvedības fiksācija, nevis pareizs biznesa aprēķins.**
- Apstiprinātie noteikumi nāk no ChatGPT (arhitekta) komentāra Issue #2. Tie nav ņemti no MLK dokumenta; ja MLK noteikumi atšķiras, jāpielabo.

## Apstiprinātie noteikumi (ChatGPT, 2026-11-25)

| Noteikums | Vērtība |
|---|---|
| Perimetra sijas | 200 × 240 mm |
| Šķērssijas | 45 × 240 mm |
| 600 mm | **tīrā atstarpe** starp sijām, ne ass solis |
| Ass solis 45 mm sijām | 600 + 45 = **645 mm** |
| Mērīšana | no gala sijas **iekšējās plaknes**: 600 mm brīvas atstarpes, sija, 600, sija … |
| Pēdējā atstarpe | atlikums, **bez pārdalīšanas**, bez papildu sijas |
| Gala un šķērssiju garums | **W − 400 mm** (ja perimetrs 200 mm) |
| Platums W | nav ierobežots ar 3500/4000; līdz aptuveni 4500 mm; faktiskais izmērs no rasējuma |
| Garums L | no **grīdas moduļa kontūras**, ne no jumta plāna |
| Modulis | katrs fiziskais modulis atsevišķi |
| Atlikums > 600 mm | atzīmēt pārbaudei; neizdomāt papildu siju, nepārdalīt |
| Ģeometrija | neskaidru ģeometriju prasīt apstiprināt, nevis izvēlēties |

### Formula (pārbaudīta)
brīvais garums `C = L − 400`; šķērssiju skaits `n = ⌊C / 645⌋` (k-tā sija beidzas pie 645·k mm);
atlikums `r = C − 645·n`.

## Neatkarīga pārbaude (ar roku un atsevišķu skriptu, nevis ar testējamo kodu)

ChatGPT skaitļi **apstiprinās**.

**12000 × 4000 mm:**
- C = 11600; 11600 / 645 = 17,98 → **n = 17**; 17 · 645 = 10965; atlikums **r = 635 mm**.
- 18. sija sāktos pie 600 + 17 · 645 = 11565 un beigtos pie 11610 > 11600 → neietilpst.
- r = 635 > 600 → **atzīmēt pārbaudei**.
- Garās: 2 · 0,2 · 0,24 · 12,0 = 1,152 m³; gala: 2 · 0,2 · 0,24 · 3,6 = 0,3456 m³; šķērssijas: 17 · 0,045 · 0,24 · 3,6 = 0,66096 m³.
- **Kopā 21 gab., 2,15856 m³.**

**12100 × 4000 mm:** C = 11700; n = 18 (18 · 645 = 11610); r = 90 mm. Kopā 22 gab., 1,1616 + 0,3456 + 0,69984 = **2,20704 m³**.

## Esošais kods pret apstiprināto noteikumu

| Modulis | Rādītājs | Esošais kods | Noteikums | Starpība |
|---|---|---|---|---|
| 12000 × 4000 | šķērssijas | 19 | 17 | +2 |
| | kopā gab. | 23 | 21 | +2 |
| | kopā m³ | 2,23632 | 2,15856 | **+0,07776** (+3,6 %) |
| 12100 × 4000 | šķērssijas | 20 | 18 | +2 |
| | kopā m³ | 2,2848 | 2,20704 | +0,07776 |

Kods: `ceil(L / 600) − 1`, t. i. 600 mm kā ass solis no ārmalas, un neņem vērā gala siju platumu un sijas biezumu. Pārvērtējums pieaug ar moduļa garumu.

Sakrīt ar noteikumu: garās perimetra sijas (200 × 240 × L, 2 gab.) un gala sijas (200 × 240 × W − 400, 2 gab.).

## Labojums 1. versijas kļūdai
1. versijas testa komentārā bija nepareiza nevienādība (`n·45 + (n+1)·600 ≤ 11600 ⇒ n ≥ 17,05 ⇒ 18`) — virziens bija pretējs, un "18 gab." alternatīva nebija korekta. Pareizi: pie tīrās atstarpes n = 17 (17 · 45 + 17 · 600 = 10965 ≤ 11600; 18 neietilpst). Komentārs un tests ir labots.

## Kas ir testos
`tests/test_ad_floor_frame.py`, 20 testi:
- **TestApprovedRuleReferenceModel** (4): noteikumu aritmētika ar roku aprēķinātām vērtībām; nav atkarīga no `app.py`.
- **TestADCurrentBehavior** (5): esošā uzvedība, nosaukumos atzīmēts, kas **nav apstiprināts** (`..._19_not_approved`, `..._totals_not_approved`).
- **TestADNoGuessing** (3): aprēķins netiek veikts, ja izmēri nav droši nolasāmi.
- **TestADAndPDAreSeparate** (2): AD un PD ceļi ir atsevišķi.
- **TestADApprovedRules** (6, `@expectedFailure`): sagaidāmā uzvedība pēc noteikumiem. Katrs krīt no pareiza iemesla (pārbaudīts).

| `@expectedFailure` tests | Faktiski | Sagaidāms |
|---|---|---|
| cross_joists 12000 × 4000 | 19 (kopā 23) | 17 (kopā 21; 2,15856 m³) |
| cross_joists 12100 × 4000 | 20 | 18 (2,20704 m³) |
| platums 3600 | noraidīts ar kļūdu | pieņemts, gala sijas 3200 |
| jumta pārkare 12600 | garums 12600 | 12000 |
| neviennozīmīgs platums (3500 un 4000) | kluss 3500 (gala sija 3100) | 3600 vai atteikums/apstiprinājums |
| titullapa pirms plāna | kļūda | plāns tiek atrasts |

Ja atšķirība nākotnē pazūd (kods labots), `@expectedFailure` tests kļūs par "unexpected success", un dekoratoru jānoņem; vērtības nemainīt.

## Neatrisināts / jāsaskaņo
1. **Atlikums > 600 mm** (12000 × 4000 → 635): kā atzīmēt pārbaudei lietotnē (brīdinājums, kolonna, bloķēt eksportu)? Nav testa, jo nav specifikācijas.
2. **"Aptuveni 4500 mm"**: precīza platuma robeža un ko darīt ārpus tās (atteikums vai brīdinājums).
3. **"Ja perimetrs 200 mm"**: kā noteikt perimetra sijas platumu, ja tas nav 200 mm? Pašlaik 200 ir cieti ierakstīts.
4. **Katrs fiziskais modulis atsevišķi**: kā atšķirt vairākus moduļus vienā plānā, un kā rīkoties ar L-veida plānu? Kods pieņem vienu taisnstūri.
5. **Drošā ģeometrijas izvēle**: kādi izmēru kandidāti ir pieņemami un kad jāprasa lietotāja apstiprinājums? Pašlaik izvēle ir heiristiska (`max`, biežums, garākais teksts).
6. AD ceļš neizmanto `read_pdf`, tāpēc tajā nav 100 lapu limita un paroles PDF pārbaudes.
7. Streamlit brīdinājums: `use_container_width` ir novecojis. AD testiem vajag Streamlit ar `AppTest` failu augšupielādi (pārbaudīts ar 1.67.0); ar vecāku versiju tie tiek izlaisti (`skip`).

## Ieteiktais nākamais uzdevums (atsevišķs Issue)
1. Iznest AD grīdas rāmja loģiku `src/` modulī kā tīras funkcijas (izmēru nolasīšana, šķērssiju skaitīšana pēc formulas `n = ⌊(L − 400) / 645⌋`).
2. Realizēt apstiprinātos noteikumus un atlikuma pārbaudes atzīmi.
3. Mainīt ģeometrijas izvēli: nenoteiktības gadījumā prasīt apstiprinājumu.
4. Noņemt `@expectedFailure` un pārrakstīt `TestADCurrentBehavior` pēc jaunajiem noteikumiem.
5. Salīdzināt ar reālu kontroltāmi lokāli, nepievienojot PDF GitHub.
