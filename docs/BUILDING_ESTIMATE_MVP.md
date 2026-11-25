# Pilnas ēkas materiālu tāme — MVP (Issue #12)

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

## NAV realizēts (apzināti)
Automātiska PDF → tāme; automātiska nesošo sienu/pastiprinājumu noteikšana; 45×240 īsās starpsijas; MLK receptes, cenas, normstundas; Excel formāts (ir CSV); stāvu/jumta ģeometrija (tikai ievadīti laukumi vai slīpuma formula); projekta saglabāšana/ielāde; atveru piesaiste konkrētam sienas posmam.

## Kā pārbaudīt telefonā (lokāli vai uz jūsu Streamlit adreses)
1. `streamlit run app.py` (vai `start_mlk_windows.bat`), atveriet adresi telefonā tajā pašā tīklā vai savā Streamlit lietotnē.
2. Režīmu izvēlē izvēlieties **Pilnas ēkas tāme**.
3. Spiediet **Ielādēt demonstrācijas projektu**. Augšā uzreiz parādās kopsavilkums pa grupām, koksne (8,579 m³ neto), materiālu tabula, kontroles, NAV IEKĻAUTIE darbi.
4. Atveriet sadaļas zemāk (1.–8.), mainiet, piem., sienu augstumu, jumta leņķi, slāņa biezumu vai rezerves % — rezultāts pārrēķinās.
5. Izdzēsiet jumta leņķi vai biezumu — redzēsiet «nav ievadīts» un NEPILNA TĀME.
6. **Lejupielādēt tāmi (CSV Excel)**. Spiediet **Notīrīt projektu**, lai sāktu no nulles.

## Demonstrācijas projekta kontrolvērtības
Moduļi A 12000×4000 (asis 822,5 un 1150) un B 8000×4000, novietoti galu pie gala (šuve 8 m netiek skaitīta fasādē).
Ārsienas 48 m × 2,7 m = 129,6 m²; atveres 6×(1,2×1,5)+1×(1,0×2,1) = 12,9 m²; neto 116,7 m². Iekšsienas 9,5 m × 2,7 = 25,65 m²; atveres 3×(0,8×2,1) = 5,04 m²; neto 20,61 m², abas puses 41,22 m².
Jumts 120 m² / cos 20° = 127,70 m². Grīdas neto 72 m² (terase 12 m² atsevišķi). Testi: `python -m unittest tests.test_building_estimate`.
