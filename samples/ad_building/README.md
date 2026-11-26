# Sintētiski AD ēkas paraugi (Issue #16)

**Visi dati ir izdomāti. Tie NAV reāli projekti, rasējumi, cenas vai uzņēmuma dati.** Ģenerēti deterministiski: `python -m tools.synthetic_ad_building --out samples/ad_building`.

| Fails | Saturs |
|---|---|
| `AD_sintetiska_eka.pdf` | 6 lapas: titullapa; grīdas plāns (2 moduļi, telpu eksplikācija, atveru marķējumi, fasādes kontūras teksts); logu/durvju specifikācija (dublikāts, rinda bez atrašanās vietas); sienu eksplikācija (posmi, CLT biezumi, zelmiņi, nepilna rinda); jumta plāns (2 slīpnes); konstrukciju tipi (slāņu saraksti) |
| `kontroltame_sintetiska.xlsx` / `.csv` | sintētiska Moneo kontroltāme: posmi, artikulu rindas, grupu/posma/gala kopsummas, stundu plāns/fakts, rinda bez mērvienības, rinda bez prognozes |

Lietošana: režīms «Pilnas ēkas tāme» → «0. AD PDF» (augšupielādēt PDF) vai poga «Ielādēt AD demonstrāciju»; «15. Prognozes versijas un faktiskā kontrole». Dokumentācija: `docs/AD_BUILDING_IMPORT.md`.
