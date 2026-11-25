# Reālu AD rasējumu lokālā validācija (Issue #8)

> **Šis nav automātisks pierādījums.** Sintētisku paraugu rezultāts neapliecina, ka tiks atpazīti reāli AD rasējumi. Diagnostikas rīks palīdz **uz jūsu datora** redzēt, ko analīze nolasa, un salīdzināt to ar jūsu zināmiem izmēriem. Neko neizdomā un nemaina grīdas rāmja formulu.

## 3–5 soļi
1. **Izvēlieties AD PDF** (piem., TR-126, ja tas jums ir pieejams) un turiet to lokāli. Neaugšupielādējiet to internetā un neievietojiet repozitorijā.
2. **Palaidiet diagnostiku** (Windows: divreiz noklikšķiniet `diagnostika_windows.bat` un atbildiet uz jautājumiem, vai ievelciet PDF failu uz `.bat`; rīks pats pieprasa un pārbauda PDF ceļu, lapas, kontrolizmērus un saglabāšanu; vai komandrindā `python -m tools.ad_diagnostics "C:\ceļš\TR-126_AD.pdf"`). Apskatiet lapu tabulu: klasifikators, vektoru skaits, kuras lapas analizētas. **Ja plāna lapu automātiski neatrod, norādiet to pats:** `--page 3` (lapas numuru redzat PDF skatītājā un pārskata lapu tabulā; var norādīt vairākas: `--page 3,5`).
3. **Salīdziniet ar jūsu zināmiem šī paša projekta moduļu izmēriem:** pievienojiet `--control 12000x4000` (katram modulim atsevišķi; mm). Pārskatā skaidri atdalīts, kas ir **nolasīts no PDF** un kas ir **jūsu kontrolizmērs**, kā arī novirze (mm un %) un kategorija (sakrīt / neliela / vidēja / liela / nav kandidāta). **Nesalīdziniet citu projektu AD un PD kā vienu kontroltāmi.**
4. **Reģistrējiet atšķirības** (lokāli, piem. tabulā): lapa · kandidāta ID · statuss · nolasītais L×W · jūsu kontrolizmērs · novirze · piezīme (kāpēc, jūsuprāt, atšķiras: mērogs, ķēdes izmēri, fasāde pret rāmi, terase, atrasts nepareizs modulis utt.). Ja kaut kas nav droši nolasīts, **neko neizdomājiet**: atzīmējiet "nav nolasīts".
5. **Pēc izvēles** sagatavojiet sanitizētu kopsavilkumu (`--print-summary` vai `--summary-out kopsavilkums.json`), **apskatiet to pats**, un tikai tad kopīgojiet. Rīks pats neko nesūta.

## Svarīgi ierobežojumi
- Pamatrāmis **neietver 150×240 pastiprinājumus un 45×240 īsās starpsijas**; kopējais apjoms var būt par mazu.
- Kandidāta statuss ("ģeometriski saskaņots" u. c.) **nepierāda konstrukcijas (grīdas rāmja) robežu**; pielaides ir prototipa pielaides.
- Analīze atpazīst tikai ortogonālas kontūras, izmēru norādes ar izvilkuma līnijām un 3–5 ciparu izmērus; skenēti rasējumi netiek atpazīti.

## Interaktīvais režīms un kur tiek glabāti pārskati
`diagnostika_windows.bat` palaiž fiksētu komandu `python -m tools.ad_diagnostics --interactive`; visu ievadi (arī ceļus ar atstarpēm, `&`, `%`, pēdiņām) apstrādā Python, nekas netiek likts `cmd` komandrindā. Rīks jautā: PDF ceļš → plāna lapa(s) → jūsu kontrolizmēri → vai saglabāt HTML → vai parādīt sanitizēto kopsavilkumu. Atbildes pēc noklusējuma ir "nē".
- **HTML netiek saglabāts un nekad netiek pārrakstīts bez jūsu piekrišanas:** saglabāšana notiek tikai pēc atbildes "j", katru reizi ar jaunu nosaukumu (`diagnostika_GGGGMMDD_HHMMSS.html`).
- **Pārskati (satur PDF saturu) pēc noklusējuma tiek glabāti ārpus sinhronizētām mapēm:** Windows `%LOCALAPPDATA%\MLK_diagnostika`. Ja norādāt savu mapi (`--html`, `--summary-out`) un tā šķiet OneDrive / Dropbox / Google Drive / iCloud u. c., rīks atsakās, ja vien skaidri neatļaujat ar `--allow-synced-folder`.

## Rīks: komandas
```
python -m tools.ad_diagnostics FAILS.pdf                      # pārskats konsolē; nekas netiek saglabāts
python -m tools.ad_diagnostics FAILS.pdf --page 3             # analizēt konkrētu lapu (arī ja klasifikators to neatrod)
python -m tools.ad_diagnostics FAILS.pdf --page 3 --control 12000x4000 --control 9000x3000
python -m tools.ad_diagnostics FAILS.pdf --page 3 --html D:\privati\parskats.html   # LOKĀLS HTML (satur PDF saturu; mape nedrīkst būt sinhronizēta)
python -m tools.ad_diagnostics FAILS.pdf --page 3 --print-summary                    # sanitizēts kopsavilkums apskatei
python -m tools.ad_diagnostics FAILS.pdf --page 3 --summary-out kopsavilkums.json   # saglabāt sanitizēto kopsavilkumu
python -m tools.ad_diagnostics --allowed-fields               # parādīt atļauto lauku sarakstu
python -m tools.ad_diagnostics --interactive                  # rīks pats jautā ievadi (to izmanto diagnostika_windows.bat)
```
Pēc noklusējuma rīks **neveido nevienu failu**. Izvades fails nedrīkst būt PDF un netiek pārrakstīts bez `--overwrite`.

## Sanitizētais kopsavilkums: atļautie lauki
Iekļauti **tikai** šādi lauki (to pārbauda `validate_summary`; jebkurš cits lauks vai vērtība izraisa kļūdu):

| Lauks | Saturs |
|---|---|
| `schema_version` | formāta versija (1) |
| `input_status` | ok / invalid_pdf / encrypted / too_many_pages / unreadable |
| `pages_selection` | manual / auto / all / none |
| `pages_total`, `pages_analyzed` | lapu skaits |
| `page_text_class_counts` | lapu skaits: floor / roof / list / other |
| `page_status_counts` | analizēto lapu statusu kodi: ok / no_vector_geometry / error |
| `vector_kind_counts` | vektoru veidu skaits (taisnstūra/citas kontūras, H/V/diagonāli nogriežņi, līknes) |
| `dimension_annotations_total` | izmēru norāžu skaits (bez vērtībām) |
| `candidates_total`, `status_counts` | kandidātu skaits un statusu kodi: consistent / recognised / unclear / refused |
| `reason_code_counts` | fiksēts iemeslu kodu saraksts (piem. `SCALE_CONFLICT`, `SHAPE_NOT_RECTANGLE`) |
| `excluded_counts` | izslēgto kontūru skaits pēc veida |
| `recognised_modules`, `controlled_modules` | atpazīto un kontrolēto moduļu skaits |
| `control_comparison` | noviržu kategoriju skaits: match / small / medium / large / no_candidate |

**Nekad netiek iekļauts:** faila nosaukums/ceļš, klientu un projektu nosaukumi vai identifikatori, PDF teksts un marķējumu teksti, attēli, koordinātas un lapu izmēri, faktiskie izmēri (L, W, norāžu vērtības, kontrolizmēri), PDF hash, metadati, kļūdu ziņojumu teksts. **Faktisko izmēru iekļaušana nav atbalstīta**: tai vajadzētu atsevišķu izlēmumu.

## Pilns pārskats
Konsoles un HTML pārskats **satur PDF saturu** (teksta fragmentus, izmērus, koordinātas, lapu attēlus). Tas ir paredzēts tikai jums; **nekopīgojiet un nepublicējiet**. HTML ir pašpietiekams, bez skriptiem un bez tīkla piekļuves (CSP), un viss PDF saturs tajā ir ekranēts.
