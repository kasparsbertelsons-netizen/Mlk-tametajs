# Grīdas rāmja pastiprinājumi 150×240 un shēma (Issue #10)

**Provizorisks aprēķins, nevis konstruktora specifikācija.** Pamatrāmja receptes un rezultāti nemainās (12000×4000: 21 gab., 2,15856 m³).

## Kas ir un kas NAV realizēts
- ✅ Lietotājs **pats** norāda pastiprinājuma sijas 150×240 pozīcijas katram modulim un tās **apstiprina**.
- ✅ Grafiska grīdas rāmja shēma katram aprēķinātajam modulim (mērogā, ērti telefonā).
- ❌ **Automātiska pastiprinājumu / nesošo sienu noteikšana no PDF NAV realizēta.** Nulle pastiprinājumu = tikai pamatrāmja aprēķins; tas **nepierāda**, ka pastiprinājumi nav vajadzīgi.
- ❌ **45×240 īsās starpsijas NAV realizētas** (atsevišķs uzdevums).

## Ievades konvencija
Ass = sijas **centra** koordināta garenvirzienā, **mm no moduļa ārējā gala**, tā paša gala, no kura skaita regulārās šķērssijas (shēmā augšā). Pirmās regulārās sijas ass ir 822,5 mm (pamatrāmim ar perimetru 200 mm); nākamās: +645 mm.

Pastiprinājums: 150×240 mm, garums = W − 2 × perimetra sijas platums.

## Noteikumi
| Situācija | Rezultāts |
|---|---|
| Ass **precīzi** sakrīt ar regulārās sijas asi (piem., 822,5) | pastiprinājums **aizvieto** šo regulāro siju |
| Cita brīva vieta | pastiprinājums tiek **pievienots**; regulārās sijas netiek pārbīdītas, solis netiek pārdalīts |
| 822,0 vai 823,0 (nav precīzi 822,5) | **bloķēts** (pārklājas ar regulāro siju); koordināta netiek noapaļota/piesnapota |
| Pārklājas ar citu pastiprinājumu, gala siju vai iet ārpus brīvā rāmja | **bloķēts**, tiek paskaidrots kāpēc; labojums netiek izdomāts |
| Viena un tā pati ass vairākkārt | **bloķēts** (dublikāts netiek veidots) |
| Sijas tikai pieskaras (atstarpe 0) | atļauts, brīdinājums "jāpārbauda" |
| Rāmja augstums ≠ 240 vai >20 pastiprinājumu modulī | **bloķēts** (nestandarta parametri netiek interpretēti automātiski) |

Koordināta pieņem līdz 2 zīmēm aiz komata (komats vai punkts); precīzāka ievade tiek noraidīta, nevis noapaļota.
Kontrolvērtības (12000×4000): aizvieto R1 (822,5) → 21 gab., 2,24928 m³; papildus 1150 → 22 gab., 2,28816 m³; abi → 22 gab., 2,37888 m³.

## Īsa instrukcija telefonam
1. Atver lietotni → režīms **AD**. Ievadi **L** un **W**, spied **Apstiprināt šo ievadi**.
2. Zem **"Pastiprinājuma sijas 150×240"** ievadi asis, **katru savā rindā** (piem. `822,5` un `1150`).
3. Atķeksē **"Apstiprinu pastiprinājumu pozīcijas"**. Mainot jebkuru asi, L, W vai perimetru, atzīme pazūd un jāapstiprina no jauna.
4. Zem rezultātiem redzama **shēma**: zils = regulārās, oranžs = pastiprinājums, kas aizvieto regulāro, violets = pastiprinājums papildus, zaļš = brīvās atstarpes (mm). Pa kreisi — katra pastiprinājuma ass no moduļa gala.
5. CSV lejupielāde parādās tikai, kad visi moduļi ir derīgi un apstiprināti (pretējā gadījumā — "NEPILNS APRĒĶINS").

## CSV
Vecās kolonnas nemainās (indeksi 0–10); pievienotas `Ass_no_gala_mm`, `Pastiprinajuma_avots`, `Apjoma_robeza`. Katrs pastiprinājums ir atsevišķa rinda; "KOPĀ" rinda norāda, vai apjoms ir tikai pamatrāmim vai ar lietotāja pastiprinājumiem.

## Tests
`python -m unittest tests.test_reinforcement` (kontrolvērtības, konflikti, vairāki moduļi, CSV, shēma pret aprēķinu, apstiprinājuma atcelšana). Tikai sintētiski dati.
