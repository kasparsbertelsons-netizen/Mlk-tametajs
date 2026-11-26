# AD-first tāmēšana: arhitektūras PDF → pilnas ēkas tāmes ievaddati → lokāla kontrole (Issue #16)

**Provizorisks aprēķins.** AD arhitektūras rasējums ir vienīgais projektēšanas dokuments **sākotnējā piedāvājuma** stadijā; PD/EL/virtuves detalizācija un faktiskie
patēriņi ir tikai vēlākai validācijai un kalibrēšanai. Repozitorijs ir publisks: **nekādi reāli projekta dati, failu nosaukumi, cenas, patēriņi vai rasējumi.**
Reālus datus izmantojiet tikai lokālajā versijā (`127.0.0.1`); publiskajā lietotnē — tikai sintētisko paraugu (`samples/ad_building/`).

## Plūsma (režīms «Pilnas ēkas tāme»)
1. **0. AD PDF → ievaddati**: augšupielādē AD PDF → **kandidāti** ar lauku, **lappusi**, **avotu** (vektors/teksts), **pārliecību** (augsta/vidēja/zema), pierādījumu un problēmām.
2. **Apstiprini** (atzīmē kandidātus; «droši nolasāmie» ar vienu pogu) → **Pārnest apstiprinātos uz tāmi**. Nenolasīts vai nepilns lauks netiek pārnests (nav nulle) un jāievada manuāli.
3. Papildini **receptes** (sadaļas 7b, 8, 10), katalogu un cenas (9), darbu (11) un izmaksas (12) → budžets līdz pārdošanas cenai, XLSX.
4. **15. Prognozes versijas un faktiskā kontrole**: **Fiksēt AD prognozi** → importē Moneo kontroltāmi → salīdzini → (pēc izvēles) kalibrētā versija.

## Ko atpazīst (sintētiskā parauga notācija)
Atpazīšana ir **teksta konvencijas** (pārbaudītas tikai uz sintētiska parauga; reāli rasējumi var atšķirties — tad lauki jāievada manuāli) + esošā **vektoru** analīze moduļiem.
| Kategorija | Piemērs rindai rasējuma tekstā | Kandidāts |
|---|---|---|
| Modulis (vektors) | taisnstūra kontūra ar izmēru norādēm un mērogu | L×W, pārliecība no `ad_vector` statusa |
| Telpa/terase | `Virtuve 14.0 m2`, `Terase 12.0 m2` | telpu laukumi; **terase atsevišķi**; neto grīda = telpu summa (vidēja pārliecība) |
| Fasādes kontūra | `Fasādes kontūra 20240 x 4240` | **informatīva, NAV pamatrāmis**; nobīdes netiek izsecinātas |
| Telpas augstums | `Telpas augstums 2700 mm` | noklusējuma sienu augstums |
| Sienas posms | `Siena N: ārējā, tips ĀS1, L=20.0 m, H=2700 mm, CLT 100 mm` | ārēja/iekšēja, garums, augstums, tips, CLT biezums **pa posmiem** |
| Zelmiņš | `Zelmiņš A: tips ĀS2, pamats=4.0 m, augstums=1.5 m, CLT 140 mm` | trīsstūra gala siena, ½ × pamats × augstums |
| Atvere | `L1 1200 x 1500 3 gab. ārējais posms N`, `JL1 780 x 1400 2 gab. jumta posms Slīpne A` | **ārējās / iekšējās / jumta atsevišķi**; dublikāti netiek atskaitīti divreiz; bez atrašanās vietas netiek pārnesta; skaits salīdzināts ar plāna marķējumiem |
| Jumta slīpne | `Jumta slīpne A: garums = 24.0 m, horizontālā projekcija = 2.5 m, leņķis = 20°, tips JK1, CLT 120 mm` | bruto = garums × projekcija / cos α; divslīpju jumts, CLT pa slīpnēm |
| Konstrukcijas tips | `ĀS1 Ārsiena: fasādes dēlis 20 mm; latojums 50 mm c/c 600; …; CLT 100 mm; skrūves` | tips + slāņu kandidāti (veids, biezums, solis); «abās pusēs» = ×2 |

## Ģeometrijas noteikumi
- **Jumts:** `bruto` (visas slīpnes) un `neto` (bruto − jumta logi) laukumi **atsevišķi**; jumta logi tiek atskaitīti **vienu reizi** (dublikāti izslēgti). Slāņu bāzes: «jumta neto» un «jumta bruto». Slīpne jāapstiprina.
- **Zelmiņi** ieskaitīti ārsienu bruto laukumā; **atveres** piesaistāmas posmam/slīpnei (pa tipiem un CLT biezumiem); vienīgajam posmam — automātiski; vairākiem — nepiesaistītās tiek **atzīmētas** (netiek minētas).
- **CLT biezums pa posmiem:** posma `CLT mm` → tipa CLT slānis → vispārējais biezums. Katram biezumam sava CLT rinda (cena pa artikuliem pēc biezuma).
- Moduļu L/W — tikai no apstiprināta moduļa kandidāta; ārējā fasādes kontūra netiek sajaukta ar pamatrāmi.

## Receptes pa konstrukciju tipiem (sadaļa 7b)
Tipam (`ĀS1`, `IS1`, `JK1` …) piesaistītas lietotāja rediģējamas **lokālas** materiālu receptes: vairākas atšķirīgas **latojuma** kārtas (katra ar savu soli), **plāksnes**, **siltinājums**
(m³), **apdares**, **stiprinājumu normas** (uz m²). Tipa laukums = piesaistīto posmu neto laukumi. **Normas un cenas nav izdomātas** (tukšs = «nav ievadīts»; kodā nav uzņēmuma normu).
Režīms «Pēc konstrukciju tipiem» aizstāj globālos slāņus ārsienām/iekšsienām/jumtam (nav dubultošanas); «Manuāli» saglabā iepriekšējo uzvedību. CLT slānis tipā tikai nosaka biezumu —
materiāla rindu veido CLT recepte.

## AD stadija: MEP, virtuve, mēbeles, tehnika
Šīm grupām (ventilācija, elektrība, ūdens, sanitārtehnika, iekārtas, **virtuve/mēbeles/tehnika**) AD stadijā ir **budžeta komplekti** vai **parametriskas normas** ar **skaidru pieņēmumu**
(kolonnas «Detalizācija», «AD pieņēmums»; bez pieņēmuma — brīdinājums). **Izmaksu segums** (materiāli / materiāli+montāža / ārpakalpojums) ir atsevišķs no detalizācijas: komplekts «ar montāžu» vai
ārpakalpojums grupā, kurai ir darba operācijas, tiek bloķēts kā dubultošana. Komplektiem un ārpakalpojumiem noklusējuma rezerve 0%.

## Versijas un faktiskā kontrole (lokāli)
- **Fiksēt AD prognozi**: nemainīgs momentuzņēmums (rindas, stundas, budžets, pirkstu nospiedums). Salīdzināšana notiek ar **momentuzņēmumu**, nevis dzīvo tāmi.
- **Moneo kontroltāme** (XLSX/CSV, sintētisks paraugs): artikulu rinda ≠ grupas/posma/gala kopsumma; kopsummas **netiek summētas** (tikai saskaņošanai); saglabāts artikula kods, posms, plānotais un faktiskais
  daudzums/cena/summa; **mērvienība netiek izdomāta**; stundu plāns/fakts pa posmiem. Importētie dati **neaizpilda un nepārraksta** AD prognozi.
- **Salīdzina tikai vienādu izmaksu tvērumu** (materiāli ↔ materiāli, ārējās izmaksas ↔ ārējās izmaksas, stundas ↔ stundas); mērvienības netiek konvertētas. Rādītāji: **EUR starpība** (fakts − prognoze),
  **absolūtā % novirze pret faktu** `|prognoze − fakts| / |fakts|`, **absolūto noviržu summa pa grupām**, **nesasaistītās rindas** abās pusēs.
- **Kalibrētā versija** un **PD detalizācijas kopija** ir **atsevišķas projekta kopijas** (priekšlikumi: faktiskā cena katalogā, patēriņa koeficients normām); AD projekts un tā prognoze nemainās.

## Ierobežojumi
Atpazīšana nav validēta uz reāliem AD rasējumiem; neatpazītais jāievada manuāli. Nav PD/EL automatizācijas, Moneo API integrācijas, 90% precizitātes apliecinājuma. Moneo eksporta formāts ir pieņemts
(sintētisks paraugs, izplatīti kolonnu nosaukumi); reāls eksports var prasīt kolonnu nosaukumu pielāgošanu.

## Sintētiskie paraugi un DEMO
`python -m tools.synthetic_ad_building --out samples/ad_building` → `AD_sintetiska_eka.pdf`, `kontroltame_sintetiska.xlsx/.csv`. Poga **«Ielādēt AD demonstrāciju»** izveido pilnībā cenotu projektu no šī PDF.

## Korekcija pēc ChatGPT pārbaudes (PR #17)
**Datu integritāte**
- **Moduļa identitāte nav izmērs.** Divi fiziski atšķirīgi moduļi ar vienādiem L/W tiek pārnesti abi (identitāte = PDF kontrolsumma + lappuse + kontūra/pozīcija = `source_key`);
  atkārtoti importējot to pašu avota kandidātu, modulis netiek dublēts; vienāda izmēra modulis bez šīs atslēgas (piem., manuāli ievadīts) netiek zaudēts — rāda brīdinājumu pārbaudei.
- **Salīdzināšana nedubulto prognozi.** Gan faktiskās, gan prognozes rindas vispirms tiek **agregētas pa artikulu + izmaksu segumu** (artikuls, kas izmantots vairākos posmos, netiek salīdzināts ar visu prognozes
  summu katru reizi); avota rindas saglabātas (`sources`). **Posmu sadalījums** tiek dots tikai tad, ja KATRAI prognozes un faktiskajai rindai ir posms; citādi — pa artikulu kopā.
  Atsevišķi tiek uzrādītas **sasaistīto rindu** starpības un **visa tvēruma** kopsummas (ar nesasaistītajām rindām: prognoze, fakts, starpība, nesasaistītais apjoms, pārklājums %).
  Sasaistīto rindu novirze NAV visas ēkas precizitāte.

**Moneo un stundu imports (pēc norādītās Excel STRUKTŪRAS; sintētiska kopija testiem)**
- Moneo pārskats (kolonnu burti): virsraksta rindas B=Kods, F=Apraksts (projekts/posms, posmi atkārtojas); virsrakstu bloks J/M/P/S/W/Z; artikulu rindas E=kods, H=apraksts, I/K/N=budžeta daudzums/cena/summa,
  Q/T/V=faktiskais daudzums/cena/summa; grupu rindas D/G ar O/X summām; posma kontrolsumma F=`<bez koda>`, P/Z; atkārtota kopsumma J=Kopā, P/Z. Tukšās rindas ignorē; mērvienību nav (nezināma).
  Artikulu summas tiek saskaņotas ar posmu kontrolsummām (un grupu summām), nekas netiek summēts divreiz. **Importa priekšskatījums un lietotāja kolonnu kartējums**, ja struktūra atšķiras.
- Stundu pārskats: 2 rindu virsraksts (A=Darbība, B=Stundas; nākamajā rindā B=Reāli, C=Plānots — kolonnas nosaka šī rinda), A=operācija, `Kopā:` = kontrolsumma. Salīdzina pa **operācijām** ar fiksētās prognozes
  darba operācijām (atšķirīgus nosaukumus kartē lietotājs); atkārtotas operācijas agregē.
- AD notācijas fragmenti (Revit tipa, sintētiski): telpu tabula Nr./Name/Area/Notes, «Total Building Area on Ground» (informatīvi, NAV neto grīda), logu marķējumi `W-n`/`RW-n` ar «platums x augstums mm»
  (skaits — no plāna marķējumiem; bez tā — manuāli), jumta leņķis grādos. Neskaidrais netiek pārnests.
