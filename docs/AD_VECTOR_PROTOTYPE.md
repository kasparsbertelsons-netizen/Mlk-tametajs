# AD vektoru ģeometrijas prototips (Issue #6)

**Statuss:** prototips. Sintētisku paraugu rezultāts **nav pierādījums**, ka tiks atpazīti reāli AD rasējumi. Aprēķina kodols (`src/floor_frame.py`) un PD režīms nav mainīti; `src/frame_vectors.py` ir PD siju kandidātu detektors un ar šo moduli nav saistīts.

## Moduļi
| Fails | Uzdevums |
|---|---|
| `src/ad_vector.py` | vektoru analīze: kontūras, izmēru norādes, mērogs, pierādījumi, priekšskatījums |
| `src/ad_ui.py` | kandidātu tabula, priekšskatījums, pierādījumi, L/W pārnešana (apstiprinājums obligāts) |
| `tools/synthetic_ad_pdf.py` | sintētisku vektoru PDF ģenerators |
| `samples/ad_vector/` | ģenerētie paraugi + instrukcija ([README](../samples/ad_vector/README.md)) |

## Kā tiek noteikts kandidāts
1. **Kontūras**: slēgtas ortogonālas kontūras no PDF vektoriem (`re`, `qu`, slēgtas `l` ķēdes). Lapas rāmis tiek izslēgts.
2. **Izmēru norādes**: 3–5 ciparu teksts + tuvākā nepārtrauktā izmēru līnija (≤ 14 pt) + izvilkuma līnijas abos galos. Vertikāli teksti tiek atpazīti pēc teksta virziena.
3. **Saistība ar kontūru** (telpiska): izmēru līnijas gali jāsakrīt ar kontūras malām (±2 pt) **un** abu izvilkuma līniju tuvākajiem galiem jāatrodas pie vienas šīs kontūras malas (≤ 8 pt). Ja izvilkuma līnijas ir, bet sākas citur, norāde pieder citai kontūrai un netiek ņemta. Ja izvilkuma līniju nav abos galos, sakrīt tikai koordinātas (**vāja** sasaiste): kandidāts ir "neskaidrs", jo norāde var piederēt citai kontūrai ar tādu pašu izmēru. Pierādījumos redzams, pie kuras malas un ar kādu spraugu izvilkuma līnijas sākas.
4. **Mērogs pret izmēriem**: izsecinātais mērogs = izmēra teksts / (izmērītais garums pt · 25,4/72). Virsraksta "1:xx" tiek pārbaudīts pret to (±2 %), nevis vienkārši pieņemts. Pretruna → atteikums; mērogs nav norādīts → neskaidrs; vairāki dažādi mērogi lapā → neskaidrs.
5. **Lomas**: kontūra ar marķējumu terase/telpa (vai laukums "m2") netiek uzskatīta par moduli; kontūras bez izmēru norādēm nav kandidāti (netiek izvēlēta "lielākā"); ligzdotas kontūras bez moduļa marķējuma abas ir neskaidras.
6. **Blakus kontūras**: netiek apvienotas. Robeža ir **marķēta zīmējumā** (līnija gar malu vai teksts "robeža/boundary"), nevis pierādīta konstruktīvi. Katra kopējā mala tiek vērtēta **atsevišķi**: ja modulim ir vairāki kaimiņi, viena marķēta mala nepadara skaidru citu nemarķētu malu; šis kandidāts paliek neskaidrs.
7. **Forma**: nav taisnstūris (L/U) → atteikums; automātiska sadalīšana netiek veikta.

## Statusi
| Statuss | Nozīme | Var pārnest L/W |
|---|---|---|
| ģeometriski saskaņots | taisnstūris + abas izmēru norādes telpiski saistītas ar kontūru + mērogs pārbaudīts + moduļa teksta marķējums, bez pretrunām | jā, ar brīdinājumu |
| atpazīts | tas pats bez moduļa marķējuma (var būt fasādes kontūra) | jā, ar brīdinājumu |
| neskaidrs | pierādījumu nepietiek (nav mēroga, vāja sasaiste, blakus kontūra bez marķētas robežas, ligzdotas kontūras, u. c.) | ja ir abi izmēri, ar brīdinājumu |
| atteikums | neregulāra forma vai mēroga pretruna | nē |

**Neviens statuss nepierāda, ka kontūra ir grīdas rāmja (nevis fasādes) konstrukcijas robeža.** Teksts "MODULIS" kontūras iekšpusē ir tikai marķējums. Kandidāta kartītē vienmēr ir atruna; lietotāja apstiprinājums ir obligāts. **Pielaides (±2 pt, ±2 %, 8 pt) ir tikai prototipa pielaides**, nevalidētas uz reāliem rasējumiem.

Pierādījumi katram kandidātam: lapas nr., bbox/virsotnes (pt), līnijas biezums, katras izmēru norādes vērtība, teksta bbox, izmērītais garums, izsecinātais mērogs, mēroga avots un pārbaudes rezultāts, moduļa marķējums, kaimiņi un robežas pierādījums, problēmu saraksts.

## Lietotnes plūsma un drošība
Kandidāti netiek apstiprināti automātiski. "Pārnest" aizpilda L, W un avotu (`PDF n. lapa, vektoru kandidāts Pn-Kk`) un **katrā pārnešanā dzēš šī moduļa apstiprinājumu** (arī tad, ja pārnesta tā pati vērtība); apstiprinājums jāizdara atsevišķi, un jebkura ievades maiņa to atceļ. Ja L/W pēc pārnešanas atšķiras no kandidāta, avots tiek marķēts kā **"manuāli koriģēts"**. Viens kandidāts nevar tikt ieskaitīts divos moduļos (dublikāts tiek bloķēts; atsevišķam modulim jāizvēlas manuāls avots). Analīzes rezultāts glabājas tikai `st.session_state["ad_scan"]` un tiek dzēsts, mainot vai noņemot PDF; globāls kešs netiek lietots. Priekšskatījums tiek zīmēts atmiņā un netiek saglabāts.

## Ierobežojumi
- Tikai ortogonālas kontūras; kontūra, kas zīmēta no atsevišķiem nogriežņiem, netiek atpazīta (izvilkuma līnijas, kas pieskaras kontūrai, var sajaukt savienojumus).
- Izmēru ķēdes (vairāki secīgi izmēri vienai malai) netiek apvienotas; teksts, kas nav tīra 3–5 ciparu virkne (piem., "12 000", "L=12000"), netiek lasīts.
- Telpas un terases tiek izslēgtas pēc teksta marķējuma kontūras iekšpusē; bez marķējuma tās var parādīties kā neskaidri kandidāti.
- Rastra (skenēti) rasējumi netiek atpazīti.
- Rezultāts balstīts uz sintētiskiem paraugiem; reālo AD rasējumu validācija ir nākamais posms.
- Izvilkuma līniju sasaiste nosaka tikai, pie kuras kontūras malas tās sākas; ķēdes un sarežģītas CAD konvencijas netiek interpretētas.

## Nākamie soļi
1. Praktisks sintētisks tests Streamlit (lokāla instance) un merge ar lietotāja apstiprinājumu.
2. **Lokāls rīks reāliem AD rasējumiem** (šajā PR NAV izstrādāts): rasējums netiek publicēts; eksportētais JSON nedrīkst saturēt PDF, klientu nosaukumus vai rasējuma teksta fragmentus. Sanitizācija jāprojektē pirms rīka izstrādes (piem., tikai skaitliskie pierādījumi un statusi, bez marķējumu un telpu nosaukumu teksta).
3. Atsevišķi 150×240 pastiprinājumi un 45×240 īsās starpsijas.
