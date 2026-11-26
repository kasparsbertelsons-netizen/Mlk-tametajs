# Pilnas ēkas materiālu tāme — MVP (Issue #12): CLT-first, vienots BOM

**PROVIZORISKA materiālu tāme, nevis gala piedāvājums.** Nepilna tāme tiek skaidri marķēta kā NEPILNA un netiek rādīta kā pilna.
Repozitorijs ir publisks: demonstrācijas projekts ir **sintētisks** (nav MLK dati, cenas vai rasējumi).

## Ko dara
Jauns režīms **«Pilnas ēkas tāme»** (zem režīmu izvēles). Visi ievaddati ir lietotāja ievadīti; PDF nav obligāts un šajā režīmā netiek nolasīts.
Esošie režīmi AD, PD un lokālā diagnostika nav mainīti. Grīdas rāmis = esošais kodols (`src/floor_frame.py`, ar Issue #10 pastiprinājumiem) bez izmaiņām.

| Grupa | Ko skaita |
|---|---|
| Grīda | rāmja koks pa moduļiem (kodols), PIR brīvajās zonās (biezums rediģējams, sākotnēji 200 mm), grīdas plātne (Σ L×W), grīdas apdare (neto platība) |
| Ārsienas | fasāde, latojums, vēja plēve, karkasa pildījums, tvaika plēve, 50 mm instalāciju slānis, iekšējā apdare (neto bez atverēm); karkasa koks, ja ievadīts šķērsgriezums un solis |
| Iekšsienas | pildījums, apdare abās pusēs (2 × neto), karkasa koks |
| Jumts | seguma platība (faktiskā vai apstiprināts slīpuma aprēķins = projekcija / cos leņķis), siltinājums, membrāna, latojums, segums, spāres (provizoriski) |
| Logi un durvis | gabali pa izmēriem; laukums tiek atskaitīts ārsienu vai iekšsienu grupā |
| Iekšējā apdare | griestu apdare (grīdas apdare ir grupā «Grīda», sienu apdare — sienu grupās: nekas netiek skaitīts divreiz) |
| Terases | atsevišķi, ārpus iekštelpu platības |
| Manuālās rindas | jebkurš neautomatizēts apjoms (vannasistaba, MEP u.c.), marķēts «manuāli» |

Tabulā katrai rindai: materiāls, **neto** daudzums, vienība (m², m³, m, gab.; vienības netiek apvienotas), **rezerve %** (rediģējama, noklusējums 10%, nošķirta no neto), **pasūtāmais**, aprēķina pamats, avots/pieņēmums, statuss (`ievadīts`, `pieņēmums (nav apstiprināts)`, `nav ievadīts`, `manuāli`, `izslēgts (dublikāts)`).
Kopsavilkums pa grupām rāda statusu, koksni m³ (neto/pasūtāmā), izmaksas un stundas (tikai ievadītās). Dažādu materiālu m² netiek summēti.

## Svarīgākie noteikumi
- Trūkstošs izmērs/parametrs = **«nav ievadīts»** + brīdinājums, nekad pieņēmums. Noklusējuma slāņu saraksts satur tikai nosaukumus; biezumus un soļus ievada lietotājs (izņemot Issue norādītos: PIR 200 mm, instalāciju slānis 50 mm, sienu augstums 2700 mm kā rediģējams orientējošs).
- Karkasa šķērsgriezums un solis nav apstiprināti, kamēr tos neievada (statuss «pieņēmums»). Spāres: garums = jumta platība / solis (provizoriski). Karkasa koks: statņi ⌈garums/solis⌉+1 katram posmam + 2 papildu statņi uz atveri, laidi 2 × garums, atveru sijas 2 × platums.
- Kopīgās moduļu šuves nav fasāde: ievadi FAKTISKĀS ārsienu garumus. Ja garums pārsniedz moduļu perimetru — kļūda; ja vienāds ar to (vairāki moduļi) — brīdinājums par šuvēm.
- Atveru laukums ≥ sienu bruto laukumam — kļūda, neto netiek rādīts.
- Modulis tiek skaitīts tikai ar atzīmi «Apstiprināts»; mainot L, W vai pastiprinājumu asis, apstiprinājums tiek atcelts.
- Slānis (nosaukums + pamats) netiek ieskaitīts divreiz; dublikāts tiek izslēgts ar brīdinājumu.
- Cenas un darba stundas — tikai manuāli («Cenas un darba stundas» sadaļa); nav MLK cenu. Izmaksu summa ir nepilna, ja daļai rindu nav cenas.
- CSV: virsraksts «PROVIZORISKA … NAV GALA PIEDĀVĀJUMS», statuss (NEPILNA / ievaddati ievadīti), visas rindas, nepilnās sadaļas un **NAV IEKĻAUTIE darbi** (rediģējami).
- Projekta dati ir tikai sesijā; netiek sūtīti un saglabāti.

## 2. posms: CLT māja, BOM, receptes, budžets (ChatGPT komentāri Issue #12)
**Vienota arhitektūra** (nav divu sistēmu): kopīga projekta ģeometrija (moduļi, sienas, atveres, jumts) → **konstrukciju receptes** (CLT — pamata,
koka karkass — 2. posms, esošais kods saglabāts) → **BOM** (vienots materiālu saraksts) → budžeta kopsavilkums → CSV.
Konstrukcijas tipu izvēlas režīma augšā; CLT un karkasa **slāņu saraksti ir atšķirīgi** (karkasa recepte netiek uzskatīta par CLT recepti).
Tipu mainot, slāņu saraksts tiek aizstāts ar attiecīgā tipa noklusējumu (ar brīdinājumu).

### CLT recepte (sadaļa 2b)
Ārsienu/iekšsienu (un pēc izvēles jumta/grīdas) CLT paneļi: **neto laukums (bez atverēm) × lietotāja ievadīts un apstiprināts biezums → m² un m³**.
Cena tiek piesaistīta **tikai izvēlētajai vienībai** («Cena pēc» m² vai m³); otra vienība tiek rādīta kā «alternatīvā (nav cenota)», tāpēc izmaksas
netiek dubultotas. **CLT rezerve** ir regulējama atsevišķi (10% — provizorisks pieņēmums). Biezums nav izdomāts: tukšs = «nav ievadīts»; ievadīts,
bet neapstiprināts = «ievadīts (nav apstiprināts)». Atgriezumu/optimizācijas algoritms NAV realizēts. Jumta/grīdas konstrukciju lietotājs izvēlas
pēc projekta (CLT jumta paneļi vai spāres); koka grīdas pamatrāmis (esošais kodols) ir izslēdzams.

### BOM rindas datu modelis
Katrai rindai: **artikuls**, materiāla nosaukums, **specifikācija**, mērvienība, **neto daudzums**, **rezerve %**, **pasūtāmais**, **iepakojums**
(ja zināms: pasūtāmais tiek noapaļots uz augšu līdz iepakojumam), **cena** (+ izmaksas), **modulis/telpa/sistēma**, **konstrukciju grupa**,
**ražošanas posms**, avots/pieņēmums, apstiprinājums (apstiprināts / nav apstiprināts / — atvasināts no ģeometrijas) un statuss.
**Ražošanas posmu klasifikācija NAV izstrādāta**: lauks ir brīvs teksts, lietotājs to nodefinēs vēlāk. Nezināms nav nulle (tukšs, nevis 0,00).

### Receptes ar patēriņa normām (sadaļa 8)
Materiāls × **patēriņa norma** uz pamata vienību (m² ārsienu/iekšsienu/jumta/grīdas/griestu, m ārsienu/iekšsienu garuma, gab. logu/durvju/moduļu)
**vai tiešs daudzums**. Normas netiek izdomātas: tukša norma = «nav ievadīts» + brīdinājums. Skrūvju solis, iekārtu modelis, MEP trasējums un
faktiskās MLK normas ir **lietotāja ievadāmi**. Demonstrācijas normas ir sintētiskas («DEMO»).

### Materiālu katalogs (sadaļa 9) un cenas
Neobligāts artikulu katalogs (nosaukums, specifikācija, vienība, cena, iepakojums): artikuls aizpilda tukšos laukus, un kataloga cena attiecas uz visām
rindām ar šo artikulu, ja vienības sakrīt (citādi brīdinājums). Rindā ievadīta cena ir svarīgāka par kataloga cenu. Sasaiste ar MLK/Moneo artikuliem —
nākamajos posmos (šajā posmā tikai teksts, bez API).

### Budžeta kopsavilkums
Materiāli (**tikai rindas ar ievadītu cenu**) + **citas izmaksas** (MEP darbs, transports, montāža, pieskaitāmās, atlīdzība — sākumā NAV ievadītas un NAV
iekļautas). Kopsumma tiek marķēta **NEPILNS**, ja ir rindas bez cenas, neievadītas citas izmaksas, obligātās grupas bez datiem vai kļūdas.

### Grupu pārklājums un iepirkuma gatavība
Obligātās BOM grupas: grīda, ārsienas, iekšsienas, jumts, logi un durvis, iekšējā apdare, stiprinājumi un palīgmateriāli, ventilācija,
elektroinstalācija, ūdens un kanalizācija, sanitārtehnika, iekārtas un kondicionēšana. Grupa bez ieraksta = «NAV IEVADĪTS». Saraksts ir
**«NAV GATAVS IEPIRKUMAM»**, kamēr nav (1) atbildīgās personas vārda un apstiprinājuma (sadaļa 10) un (2) visu obligāto grupu pārklājuma bez trūkstošiem
datiem; arī tad apjomi paliek **AD stadijas provizoriski** (atšķiras no PD/MEP un apstiprinātu recepšu stadijas).

### Nākamajiem posmiem
Detalizētas stiprinājumu un inženiertīklu recepšu automātika, iepakojumu optimizācija, MLK/Moneo artikulu sasaiste, ražošanas posmu klasifikācija,
CLT atgriezumu optimizācija, koka karkasa mājas pilna receptes pārbaude.

## 3. posms (Issue #14): cenu imports, darba pašizmaksa, budžets līdz pārdošanas cenai, XLSX, projekta saglabāšana
### Cenu/artikulu kataloga imports (sadaļa 9)
Lokāla XLSX/CSV augšupielāde (fails tiek lasīts atmiņā, nekas netiek sūtīts). Kolonnas: **Artikuls, Nosaukums, Specifikācija, Mērvienība,
Vienības cena EUR bez PVN, Iepakojums, Piegādātājs** (pēdējais pēc izvēles; atpazīst arī īsos nosaukumus). Lejupielādējams sintētisks šablons (XLSX/CSV).
- **Artikuls = teksts** (CSV un teksta šūnās sākuma nulles saglabājas; skaitliska XLSX šūna tiek atzīmēta ar brīdinājumu).
- **Trūkstoša cena = tukša, nevis 0**; cena 0 tiek atzīmēta ar brīdinājumu. Negatīva/nederīga cena, cena bez mērvienības, dublikāts artikuls, formulu šūnas
  (netiek izpildītas) — rinda netiek importēta un parādās kļūdu sarakstā.
- Priekšskatījums rāda derīgās rindas, kļūdas, jaunus/atjaunināmus/nemainītus artikulus, **nesaistītus artikulus** (neviena tāmes rinda tos nelieto) un
  tāmes artikulus, kuru nav failā. **Mērvienības netiek konvertētas**: ja importa vienība neatbilst tāmes rindām ar šo artikulu, rinda netiek piemērota
  (ne cena, ne vienība). Piemērošanai vajadzīgs apstiprinājums. Tukšs importētais lauks neizdzēš esošu cenu.

### Stabila rindas identitāte (cenu atslēga)
Katrai rindai ir stabils `id` (nevis `grupa|nosaukums`). Cena tiek piesaistīta rindas `id` un **parakstam (vienība | artikuls | specifikācija)**: ja tie mainās,
cena netiek piemērota (brīdinājums). Tāpēc vienādi nosaukumi ar atšķirīgiem artikuliem/specifikācijām/vienībām nepārņem svešu cenu; rindas pievienošana vai
kārtības maiņa cenas nepārbīda.

### Darba operācijas un pašizmaksa (sadaļa 11)
Tabula: grupa, **ražošanas posms (brīvs lauks)**, modulis (pēc izvēles), apjoma pamats (ģeometrija vai tiešs daudzums), **normstundas uz vienību VAI tiešas
stundas** (abas kopā — kļūda, lai darbs netiktu ieskaitīts divreiz), likme EUR/h (kopējā pilnā darba pašizmaksas likme vai rindas likme). Trūkstoša norma, apjoms
vai likme tiek marķēta, nulle netiek pieņemta. Atkārtota tā pati operācija (grupa + nosaukums + modulis + posms) netiek skaitīta divreiz; darba stundas
materiālu/receptes rindās («h», «stundas») tiek bloķētas. Ārpakalpojums ar grupu, kurā jau ir darba operācijas, tiek bloķēts kā dubultošana.

### Budžeta formulas (sadaļa 12) — vienāda secība visur
`Materiāli (pasūtāmais × cena) + Darbs (stundas × likme) + Ārpakalpojumi + Transports + Montāža + Cits = TIEŠĀS`;
`+ Pieskaitāmās (% no tiešajām) = PAŠIZMAKSA`;
**Uzcenojums** `u`: `cena = pašizmaksa × (1 + u)` **VAI Peļņas marža** `m` (daļa no cenas): `cena = pašizmaksa / (1 − m)`, `m < 100%`. Tās ir DIVAS atšķirīgas formulas
(20% uzcenojums ≠ 20% marža). `PVN = cena × likme` (pēc izvēles, likme jāievada). Zināmie un nezināmie lielumi: nezināms nav nulle; budžets tiek marķēts NEPILNS, ja
trūkst cenu, darba datu, citu izmaksu, pieskaitāmo, cenojuma, obligāto grupu vai ir kļūdas. Rezerve: materiāliem rediģējami 10%; iekārtām, logiem/durvīm,
sanitārtehnikai pēc noklusējuma 0%. CLT neto ģeometrija atšķiras no iepirkuma bruto/izgriezumiem — rezerve ir lietotāja regulējama, optimizācija nav realizēta.

### Excel (XLSX) eksports
Īsts .xlsx (openpyxl; atkarība `requirements.txt`). Lapas: **Kopsavilkums**, **Klienta piedāvājums** (bez pašizmaksām, stundām, likmēm, uzcenojuma/maržas, materiālu cenām),
**Materiālu tāme**, **Iepirkumi** (artikuls, specifikācija, vienība, neto, rezerve, pasūtāmais, iepakojums, cena, modulis, posms, statuss; rindas netiek apvienotas,
ir rindas ID), **Darba operācijas**, **Pieņēmumi un neiekļautais**. Skaitļi ir skaitļu šūnas; trūkstošs = «nav ievadīts». Visas teksta šūnas ir TEKSTS (arī, ja
sākas ar `=`, `+`, `-`, `@`): formulas netiek izpildītas. Nepilnība un DEMO tiek skaidri norādīta; nepilns/provizorisks budžets netiek dēvēts par gala piedāvājumu.
Joprojām pieejams arī BOM CSV.

### Projekta saglabāšana (sadaļa 13)
JSON lejupielāde/augšupielāde lokāli (bez servera, bez PDF, bez automātiskas sūtīšanas). Fails: `schema_version`, projekta dati (ievaddati, katalogs, receptes,
darbaspēks, cenas) un kontrolsumma. Imports validē struktūru/tipus/izmērus, aizpilda trūkstošos laukus, ignorē nezināmus laukus (ar paziņojumu), piešķir trūkstošos rindu ID.
**Gatavības statuss netiek uzticēts**: atbildīgās personas pārbaude vienmēr tiek atcelta; ja kontrolsumma neatbilst (fails mainīts ārpus programmas), tiek atceltas
arī visas apstiprinājuma atzīmes. Demonstrācijas projekts saglabājas un atjaunojas ar identisku rezultātu.

### Atbildīgās personas pārbaude (sadaļa 14)
Apstiprinājums attiecas uz konkrētu datu stāvokli (pirkstu nospiedums): jebkura datu izmaiņa (cena, norma, katalogs, ģeometrija …) to atceļ.

## Dati un piekļuve (svarīgi)
**Reālus MLK datus (cenas, normas, projektus) izmantojiet TIKAI lokālajā versijā** (`start_mlk_windows.bat` / `streamlit run app.py`, adrese **127.0.0.1** savā datorā).
**Lokālā versija nav pieejama no telefona** (127.0.0.1 ir tikai pašas ierīces adrese). **Telefonā** var atvērt tikai publiski izvietotu Streamlit lietotni (`docs/DEPLOY.md`) —
tajā drīkst izmantot **tikai sintētiskus DEMO datus**; repozitorijs un publiskā lietotne nedrīkst saturēt MLK cenas, klientu failus vai reālus projektus.

## Telefonā: demonstrācija līdz pārdošanas cenai (publiska DEMO lietotne)
1. Režīms **Pilnas ēkas tāme** → **Ielādēt demonstrācijas projektu** (viens klikšķis; sintētiska CLT māja, pilnībā cenota).
2. Augšā: budžeta tabula (materiāli, darbs, ārpakalpojumi, transports, montāža, pieskaitāmās, pašizmaksa, uzcenojums, pārdošanas cena, PVN, summa ar PVN), «Pašizmaksa» un
   «Pārdošanas cena bez PVN», DEMO brīdinājums, «NAV GATAVS IEPIRKUMAM», grupu pārklājums, materiālu tabula.
3. **Lejupielādēt Excel (XLSX)** — atveriet failu: lapas Kopsavilkums, Klienta piedāvājums, Materiālu tāme, Iepirkumi, Darba operācijas, Pieņēmumi.
4. Mainiet kaut ko (CLT biezumu 2b, normu 8., darba likmi 11., uzcenojumu 12.) — rezultāts pārrēķinās. Izņemiet cenu katalogā (9.) — budžets kļūst NEPILNS.
5. **Saglabāt projektu (JSON)** un 13. sadaļā **Atjaunot** — rezultāts identisks. 9. sadaļā var lejupielādēt cenu šablonu un augšupielādēt savu XLSX/CSV (DEMO datiem).

## Lokāli ar reāliem datiem (rīt)
1. Palaidiet lokāli (127.0.0.1). 2. 9. sadaļā augšupielādējiet MLK cenu XLSX/CSV pēc šablona (artikuls kā teksts, cena EUR bez PVN, trūkstošā cena — tukša). 3. Ievadiet
darba likmi un operāciju normas (11.), citas izmaksas un cenojumu (12.). 4. Saglabājiet projektu JSON savā datorā; neievietojiet to GitHub.

## NAV realizēts (apzināti)
Automātiska PDF → tāme; automātiska nesošo sienu/pastiprinājumu noteikšana; 45×240 īsās starpsijas; MLK receptes, cenas, normstundas (tikai lietotāja ievade/imports); stāvu/jumta ģeometrija (tikai ievadīti laukumi vai slīpuma formula); atveru piesaiste konkrētam sienas posmam; Moneo integrācija; ražošanas posmu klasifikācija; CLT paneļu optimizācija; detalizēta MEP/stiprinājumu automātika; 90% precizitātes pierādījums.

## Demonstrācijas projekta kontrolvērtības (ģeometrija)
Moduļi A 12000×4000 (asis 822,5 un 1150) un B 8000×4000, novietoti galu pie gala (šuve 8 m netiek skaitīta fasādē).
Ārsienas 48 m × 2,7 m = 129,6 m²; atveres 6×(1,2×1,5)+1×(1,0×2,1) = 12,9 m²; neto 116,7 m². Iekšsienas 9,5 m × 2,7 = 25,65 m²; atveres 3×(0,8×2,1) = 5,04 m²; neto 20,61 m², abas puses 41,22 m².
Jumts 120 m² / cos 20° = 127,70 m². Grīdas neto 72 m² (terase 12 m² atsevišķi). Testi: `python -m unittest tests.test_building_estimate`.

## Demonstrācijas projekta sagaidāmās summas (DEMO, EUR; neatkarīgi rēķinātas testos)
| Pozīcija | Summa |
|---|---|
| Materiāli (pasūtāmais × DEMO cena), 35 rindas | 47 955,46 |
| Darbs: 413,30 h × 32,00 EUR/h (15 operācijas) | 13 225,49 |
| Ārpakalpojumi 650 + transports 1 850 + montāža 5 400 | 7 900,00 |
| **Tiešās izmaksas** | 69 080,95 |
| Pieskaitāmās 8 % | 5 526,48 |
| **Pašizmaksa** | 74 607,43 |
| Uzcenojums 15 % → **pārdošanas cena bez PVN** | **85 798,54** |
| PVN 21 % | 18 017,69 |
| **Summa ar PVN** | **103 816,24** |
Visi skaitļi ir sintētiski (nav MLK dati). Testi: `python -m unittest tests.test_budget_pricing tests.test_catalog_import tests.test_project_io tests.test_xlsx_export`.

## 4. posms (Issue #16): AD-first
AD PDF → kandidāti → apstiprināšana → tāme; zelmiņi, jumta slīpnes (bruto/neto), CLT biezumi pa posmiem, receptes pa konstrukciju tipiem, AD komplekti/normas ar pieņēmumu, fiksēta AD prognoze un lokāla
faktiskā kontrole (Moneo kontroltāme). Pilns apraksts: `docs/AD_BUILDING_IMPORT.md`. AD demonstrācija (sintētiska, pilnībā cenota): pašizmaksa 100 973,20; cena bez PVN 116 119,18; ar PVN 140 504,21 EUR.
