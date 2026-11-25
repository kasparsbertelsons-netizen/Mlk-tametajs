# Sintētiskie AD vektoru paraugi (praktiskai pārbaudei Streamlit lietotnē)

> **Visi šeit esošie PDF ir sintētiski**: tos ģenerē `tools/synthetic_ad_pdf.py`, tie nesatur reālus projekta vai klientu datus un katrā lapā ir marķēti "SINTĒTISKS PARAUGS". Veiksmīga šo paraugu atpazīšana **nepierāda**, ka tiks atpazīti reāli AD rasējumi. Reālus klientu PDF **nedrīkst** likt šajā mapē (tests to pārbauda).

## Kā izmēģināt Streamlit lietotnē
1. `pip install -r requirements.txt`, tad `streamlit run app.py`.
2. Izvēlies režīmu **AD — prognozēt rāmi** un augšupielādē, piemēram, `ad_vector_01_12000x4000_1to50.pdf`.
3. Sadaļā **Vektoru ģeometrijas kandidāti (prototips)** redzi kandidātu tabulu, lapas priekšskatījumu ar iezīmētu kontūru un izmēru tekstiem, kā arī pierādījumus.
4. Izvēlies kandidātu → **Pārnest L un W uz moduli (neapstiprina)**. Pārnešana tikai aizpilda ievades laukus.
   Statuss **"ģeometriski saskaņots" NEPIERĀDA, ka kontūra ir grīdas rāmja (nevis fasādes) konstrukcijas robeža**: tas nozīmē tikai, ka kontūra, izmēru norādes un mērogs ir savstarpēji saskaņoti. Atkārtota pārnešana vienmēr dzēš moduļa apstiprinājumu; viens kandidāts nevar tikt ieskaitīts divos moduļos; ja pēc pārnešanas L/W maina, avots tiek marķēts kā "manuāli koriģēts".
5. Spied **Apstiprināt šo ievadi**. Tikai pēc tam parādās aprēķins. Mainot L, W, avotu vai PDF, apstiprinājums tiek atcelts. Manuālā ievade vienmēr paliek pieejama.

## Paraugi un sagaidāmais rezultāts
| Fails | Saturs | Kandidāts(-i) | Pēc apstiprināšanas |
|---|---|---|---|
| `ad_vector_01_12000x4000_1to50.pdf` | 1. lapa titullapa, 2. grīdas plāns 1:50 (modulis 12000×4000, telpa 3500, terase 4500), 3. jumta plāns ar pārkari 12600×4600 | `P2-K1` **ģeometriski saskaņots** 12000×4000; telpa un terase izslēgtas; titullapa un jumts netiek lietoti | 17 šķērssijas, **21 gab., 2,15856 m³, atlikums 635 mm** (brīdinājums) |
| `ad_vector_02_12100x3600_1to100.pdf` | modulis 12100×3600, mērogs 1:100 | `P1-K1` **ģeometriski saskaņots** 12100×3600 | 18 šķērssijas, **22 gab., 2,09088 m³**, atlikums 90 mm |
| `ad_vector_03_two_modules_with_boundary.pdf` | divi blakus moduļi ar raustītu robežas līniju | `P1-K1` 12000×4000 un `P1-K2` 12000×3600, abi **ģeometriski saskaņoti**, atsevišķi (robeža marķēta zīmējumā) | pārnes uz 2 moduļiem: **42 gab., 4,20528 m³** (21 + 21) |
| `ad_vector_04_L_shape_unclear.pdf` | L-veida kontūra | **atteikums**: L/W netiek piedāvāti, kontūra netiek sadalīta | ievadi atsevišķus taisnstūrus manuāli |
| `ad_vector_05_scale_missing.pdf` | virsrakstā nav mēroga | **neskaidrs** 12000×4000 (mērogs izsecināts no izmēriem) | pārnešana atļauta ar brīdinājumu |
| `ad_vector_06_scale_conflict.pdf` | virsrakstā 1:100, ģeometrija 1:50 | **atteikums**: mēroga pretruna | ievadi manuāli |
| `ad_vector_07_rotated_and_vertical.pdf` | 1. lapa rotēta par 90°, 2. lapā modulis zīmēts vertikāli | abi **ģeometriski saskaņoti** 12000×4000 | kā 01 |
| `ad_vector_08_no_vector_geometry.pdf` | tikai teksts un rastra attēls | nav kandidātu, brīdinājums "nav vektoru ģeometrijas" | ievadi manuāli |
| `ad_vector_09_facade_and_inner_contour.pdf` | fasādes kontūra 12400×4400 ar iekšēju 12000×4000, bez marķējuma | abi **neskaidri** (nav pierādīts, kura ir grīdas rāmja robeža) | pārnešana atļauta ar brīdinājumu |

## Atkārtota ģenerēšana
```bash
python -m tools.synthetic_ad_pdf --out samples/ad_vector
```
Ģenerēšana ir deterministiska (bez datumiem un nejaušiem ID); `tests/test_synthetic_samples.py` pārbauda, ka šeit glabātie faili ir **bait pa baitam** ģeneratora izvade.
