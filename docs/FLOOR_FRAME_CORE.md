# Grīdas pamatrāmja aprēķina kodols un AD apstiprināšanas plūsma (Issue #4)

**Statuss:** provizorisks aprēķins, nevis konstruktora specifikācija. Ietver **tikai pamatrāmi**.
**Dati:** testos tikai sintētiski dati. Konfidenciālus rasējumus publiskā Streamlit lietotnē augšupielādēt nedrīkst, kamēr nav pārbaudīta piekļuve (skat. `docs/DEPLOY.md`); privāts GitHub repozitorijs nenozīmē privātu lietotni.

## Arhitektūra: ģeometrija atsevišķi no aprēķina
| Modulis | Uzdevums | Atkarības |
|---|---|---|
| `src/floor_frame.py` | aprēķins no **apstiprinātiem** L un W (mm) | tikai Python standarta bibliotēka |
| `src/ad_plan.py` | grīdas plāna lapas un izmēru **kandidāti** no PDF teksta | tikai `re` |
| `src/ad_ui.py` | Streamlit AD režīms: kandidāti → apstiprināšana → rezultāts | streamlit, `src/pdf_reader.py` |
| `app.py` | režīma izvēle; PD ceļš nav mainīts | |

## Aprēķina noteikumi (ChatGPT, Issue #2 un #4)
| Elements | Šķērsgriezums | Garums | Skaits |
|---|---|---|---|
| Garās perimetra sijas | 200 × 240 | L | 2 |
| Gala sijas | 200 × 240 | W − 2·200 | 2 |
| Regulārās šķērssijas | 45 × 240 | W − 2·200 | n |

- Mērījums no gala sijas **iekšējās plaknes**: 600 mm brīva atstarpe līdz pirmās šķērssijas malai, tālāk 645 mm solis.
- `n = ⌊(L − 400) / 645⌋`, atlikums `r = (L − 400) − 645·n`. Atlikums netiek pārdalīts, un sija netiek pievienota.
- **Brīdinājums "jāpārbauda"**: `r > 600`, `r = 0`, `n = 0`, `W > 4500`. Atlikums `r = 600` brīdinājumu neizraisa.
- Nulles atlikums netiek pasniegts kā konstruktīvi apstiprināts.
- Perimetrs 200×240 ir **noklusējums** (marķēts lietotnē un rezultātā), nevis nolasīts no rasējuma. Cits perimetrs tiek izmantots tikai pēc skaidra lietotāja apstiprinājuma.
- Izmēri ir veseli mm, pozitīvi, ≤ 100 000. Citādi `ValueError`.

### Pārbaudītie piemēri (roku aprēķins)
| L × W | n | Atlikums | Sijas | m³ |
|---|---|---|---|---|
| 12000 × 4000 | 17 | 635 mm (brīdinājums) | 21 | 2,15856 |
| 12100 × 4000 | 18 | 90 mm | 22 | 2,20704 |
| 12000 × 3600 | 17 | 635 mm | 21 | 2,04672 (šķērs./gala sijas 3200 mm) |
| 12000 × 4000 un 12100 × 3600 | | | 43 | 4,24944 (moduļi summēti atsevišķi) |

### Novietojums un nepārklāšanās
`calculate_module` izveido šķērssiju koordinātas (`(sākums, beigas)` mm no moduļa gala) un pārbauda tās ar `layout_problems`: katra sija atrodas starp gala sijām, atstarpes pirms katras sijas ir tieši 600 mm, pēdējā atstarpe ir atlikums, sijas nepārklājas. Iekšēja pretruna izraisa `RuntimeError`. Testi pārbauda novietojumu pār ~3900 L/W kombināciju (L no 1000 līdz 30000 ar soli 37; W = 3000, 3600, 4000, 4500, 5000).

## AD lietotnes plūsma
1. PDF **nav obligāts**. Ja augšupielādēts, tiek nolasīts ar `read_pdf` (30 MB, 100 lapas, bez paroles). Nolasītais teksts glabājas **tikai šīs sesijas `st.session_state`** un tiek dzēsts, mainot vai noņemot PDF; globāls kešs (`st.cache_data`) netiek lietots.
2. Tiek parādīts **pagaidu kandidātu saraksts** (heiristika, nevis automātiska ģeometrija) no grīdas plāna lapām ar avota lapu. Kandidāti nav ranžēti un netiek ielikti ievades laukos.
3. Netiek izmantoti: **jumta plāna** lapas, **titullapa/rasējumu saraksts** (lapa, kurā "Floor plan" minēts kopā ar jumta plānu vai saraksta atzīmi), skaitļi rindās ar **terase/terrace/veranda**. Terases tiek izslēgtas tikai pēc atslēgvārda tajā pašā rindā, tāpēc **nav garantijas, ka visas terases ir izslēgtas**; lietotājam jāpārbauda, vai L un W neietver terasi.
4. Lietotājs ievada **L un W** katram taisnstūra modulim (1–10 moduļi), izvēlas avotu un spiež **"Apstiprināt šo ievadi"**.
5. **Apstiprinājums ir piesaistīts ievades versijai**: L, W, perimetrs, avots, PDF identitāte un nestandarta/platuma atzīmes. Mainoties jebkuram no tiem, apstiprinājums tiek atcelts ("Ievade mainīta pēc apstiprinājuma") un **saglabātais nospiedums tiek dzēsts**, tāpēc atgriežoties pie sākotnējiem datiem (A → B → A, arī PDF noņemšana un atjaunošana) jāapstiprina vēlreiz. PDF identitāte ir **pilns SHA-256 no faila satura** jebkuram augšupielādētam failam, arī nederīgam vai par lielam (nekad ne tikai nosaukums + izmērs). Identiska satura PDF tieša nomaiņa apstiprinājumu saglabā, ja pārējā ievade nemainās. Moduļa nosaukums ir etiķete un nospiedumā nav iekļauts. Nestandarta perimetra un platuma atzīmes ir saistītas ar konkrēto vērtību, tāpēc mainot perimetru vai platumu tās atkal ir neatzīmētas. Noņemta moduļa apstiprinājums netiek atjaunots, pievienojot moduli atpakaļ.
6. `W > 4500` mm: brīdinājums un atsevišķs apstiprinājums; robeža nav absolūta, un 3600 mm tiek pieņemts. Perimetra platums ≠ 200 mm: nepieciešams atsevišķs apstiprinājums.
7. Rezultāts katram modulim: siju garumi, skaits, m³, atlikums, brīdinājumi, šķērssiju novietojums.
8. **Nepilns aprēķins:** ja derīgu un apstiprinātu moduļu ir mazāk nekā pieprasīts, tiek rādīts **"NEPILNS APRĒĶINS (X no Y moduļiem)"**; atsevišķu moduļu rezultāti paliek redzami, bet projekta kopsumma un CSV eksports netiek rādīti līdz visi moduļi ir derīgi un apstiprināti.
9. Pilnam aprēķinam: kopsumma un CSV (`MLK_AD_pamatramis.csv`).
10. L/U formas moduļi netiek sadalīti automātiski: ievada atsevišķus taisnstūrus.

## Ierobežojumi
- Sintētiskie PDF satur tikai tekstu, tāpēc tie **nepierāda vektoru ģeometrijas atpazīšanu**; pilna atpazīšana nav šī posma uzdevums.
- Pastiprinājumi 150×240 un 45×240 īsās starpsijas netiek noteiktas un netiek ieskaitītas; kopējais apjoms var būt par mazu.
- Terases tiek izslēgtas tikai tad, ja atslēgvārds ir **tajā pašā teksta rindā** ar skaitli (tests `test_terrace_label_on_a_separate_line_is_not_excluded` to fiksē). Citādi skaitlis paliek kandidātu sarakstā, bet nekad netiek izvēlēts automātiski.
- Netiek atpazīti izmēri ar tūkstošu atdalītāju ("12 000") un ārpus 2000–20000 mm; lietotājs tos ievada pats.
- Zāģēšanas atgriezumi, savienojumi un stiprinājumi netiek ieskaitīti.

## Vecās uzvedības labojumi (Issue #2 audits)
| # | Problēma | Stāvoklis |
|---|---|---|
| 1 | Šķērssiju skaits `ceil(L/600) − 1` | novērsts (`⌊(L − 400)/645⌋`), L = 12100 → 18 |
| 2 | Jumta pārkare maina garumu | novērsts: jumta lapas netiek lietotas |
| 3 | Platumu izvēlas pēc biežuma, W = 3600 noraidīts | novērsts: nekas netiek izvēlēts automātiski, W = 3600 pieņemts |
| 4 | Titullapa var tikt izvēlēta par plānu | novērsts: titullapa/saraksts tiek izslēgti, rezultātu tik un tā dod tikai lietotāja apstiprinājums |
| 5 | AD ceļā nebija 100 lapu un paroles pārbaudes | novērsts: AD izmanto `read_pdf` |

Visi `@expectedFailure` testi ir aizstāti ar parastiem testiem pēc faktiskas problēmas novēršanas; neviens tests netiek izlaists.

## Testēšanas vide
Python 3.13, Streamlit 1.67.0, PyMuPDF 1.28.2; `requirements.txt` zemākās versijas ir šīs. `TestEnvironment` pārbauda, ka uzstādītās versijas atbilst `requirements.txt`, un ka AppTest atbalsta failu augšupielādi; citādi testi krīt, nevis tiek izlaisti.
