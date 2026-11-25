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

### Nākamajiem posmiem (NAV šajā PR)
Detalizētas stiprinājumu un inženiertīklu recepšu automātika, iepakojumu optimizācija, MLK/Moneo artikulu sasaiste, ražošanas posmu klasifikācija un
darba stundu/pašizmaksas aprēķins, CLT atgriezumu optimizācija, koka karkasa mājas pilna receptes pārbaude.

### Telefonā: CLT demonstrācija
1. Režīms **Pilnas ēkas tāme** → **Ielādēt demonstrācijas projektu** (sintētiska CLT māja; konstrukcijas tips = CLT).
2. Augšā: budžets (96 EUR tikai no kataloga cenas skrūvēm — pārējais NEPILNS), «NAV GATAVS IEPIRKUMAM», grupu pārklājums (visas 12 grupas ar datiem),
   koksne 32,563 m³, materiālu tabula (CLT paneļi ar m² un m³).
3. Sadaļa **2b**: mainiet CLT biezumu vai «Cena pēc» (m² ↔ m³); **8**: mainiet normu vai izdzēsiet vērtību → «nav ievadīts»; **Cenas un darba stundas**: ievadiet
   cenu (budžets pārrēķinās); **10**: ievadiet «Citas izmaksas», pārbaudītāja vārdu un atzīmi.
4. **Lejupielādēt tāmi (CSV Excel)** — BOM ar visām kolonnām, budžetu, grupu pārklājumu un NAV IEKĻAUTAJIEM darbiem.

## NAV realizēts (apzināti)
Automātiska PDF → tāme; automātiska nesošo sienu/pastiprinājumu noteikšana; 45×240 īsās starpsijas; MLK receptes, cenas, normstundas; Excel formāts (ir CSV); stāvu/jumta ģeometrija (tikai ievadīti laukumi vai slīpuma formula); projekta saglabāšana/ielāde; atveru piesaiste konkrētam sienas posmam.

## Kā pārbaudīt telefonā (lokāli vai uz jūsu Streamlit adreses)
1. `streamlit run app.py` (vai `start_mlk_windows.bat`), atveriet adresi telefonā tajā pašā tīklā vai savā Streamlit lietotnē.
2. Režīmu izvēlē izvēlieties **Pilnas ēkas tāme**.
3. Spiediet **Ielādēt demonstrācijas projektu**. Augšā uzreiz parādās kopsavilkums pa grupām, koksne (32,563 m³ neto, CLT demonstrācija), materiālu tabula, kontroles, NAV IEKĻAUTIE darbi.
4. Atveriet sadaļas zemāk (1.–8.), mainiet, piem., sienu augstumu, jumta leņķi, slāņa biezumu vai rezerves % — rezultāts pārrēķinās.
5. Izdzēsiet jumta leņķi vai biezumu — redzēsiet «nav ievadīts» un NEPILNA TĀME.
6. **Lejupielādēt tāmi (CSV Excel)**. Spiediet **Notīrīt projektu**, lai sāktu no nulles.

## Demonstrācijas projekta kontrolvērtības
Moduļi A 12000×4000 (asis 822,5 un 1150) un B 8000×4000, novietoti galu pie gala (šuve 8 m netiek skaitīta fasādē).
Ārsienas 48 m × 2,7 m = 129,6 m²; atveres 6×(1,2×1,5)+1×(1,0×2,1) = 12,9 m²; neto 116,7 m². Iekšsienas 9,5 m × 2,7 = 25,65 m²; atveres 3×(0,8×2,1) = 5,04 m²; neto 20,61 m², abas puses 41,22 m².
Jumts 120 m² / cos 20° = 127,70 m². Grīdas neto 72 m² (terase 12 m² atsevišķi). Testi: `python -m unittest tests.test_building_estimate`.
