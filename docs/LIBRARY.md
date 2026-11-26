# Recepšu, cenu un normstundu bibliotēka (Issue #20)

Lokāls, atkārtoti lietojams bibliotēkas fails (JSON) — **atsevišķs no projekta un no faktiskās kontroltāmes**. Bibliotēka satur katalogu ar cenām, receptes,
normstundas un AD komplektus. Sintētisks paraugs: `samples/library/biblioteka_sintetiska.json` (ģenerē `python -m tools.synthetic_library`).
**Paraugā nav MLK datu**; reālas bibliotēkas lietot tikai lokāli (`docs/LOCAL_WINDOWS.md`) un nekad nepublicēt repozitorijā.

## Kā tas iekļaujas esošajā arhitektūrā
Piemērošana **neievieš jaunu aprēķina ceļu**. Bibliotēkas ieraksti tiek pārvērsti par esošajām projekta rindām: `recipes`, `labour.operations`, `catalog`.
Tās aprēķina `building_estimate.estimate()` kā jebkuras citas receptes (draiveris × norma, rezerve, cena no kataloga, stundas). Rindas ar bibliotēkas izcelsmi
ir atzīmētas ar `lib_code` (un komplektiem `lib_kit`), tāpēc atkārtota piemērošana tās **atjaunina vietā** (ar to pašu `id`), nevis pievieno otrreiz.
Faila validācija un kontrolsumma darbojas kā `project_io` (tikai `json`, nekad pickle/eval; ≤5 MB; mainīts fails → visi apstiprinājumi kļūst «neapstiprināts»).

## Faila struktūra (`schema_version` 1, `app` = `mlk-tametajs-biblioteka`)
| Sadaļa | Lauki |
|---|---|
| `meta` | `name`, `version`, `description`, `synthetic` |
| `catalog` | `article`, `name`, `spec`, `unit`, `unit_price`, `pack_size`, `supplier`, `price_valid_from`, `price_valid_to` (GGGG-MM-DD), `price_source` |
| `recipes` | `code`, `group`, `name`, `article`, `unit`, `driver`, `norm`, `qty`, `waste_pct`, `pack_size`, `status`, `kind`, `source`, `assumption`, `detail`, `cost_scope` |
| `labour` | `code`, `group`, `name`, `stage`, `driver`, `unit`, `norm_h`, `status`, `kind`, `source` (likme EUR/h paliek projektā) |
| `kits` | `code`, `group`, `name`, `levels`, `default_level`, `assumption`, `cost_scope`, `covers`, `positions[]` (`code`, `name`, `unit`, `qty` vai `driver`+`norm`, `options{līmenis: artikuls}`, `opening`) |

Atļautās mērvienības: `m²`, `m³`, `m`, `gab.`, `kompl.`, `kg`, `l`, `iep.`, `rit.`, `pāri`. Darba stundas (`h`) receptēs nav atļautas (tās ir sadaļā `labour`).

## Importa noteikumi (nekas netiek izdomāts)
- **Nezināma mērvienība, grupa, draiveris, statuss, veids, nederīgs datums vai negatīva cena** → ieraksts tiek noraidīts ar paskaidrojumu; pārējie ieraksti tiek saglabāti.
- **Trūkstoša cena vai norma paliek tukša** (tāme rāda «nav ievadīts»); cena bez avota rada brīdinājumu.
- **Cenas derīgums:** cena tiek piemērota tikai, ja `price_valid_from` ≤ šodien ≤ `price_valid_to` (tukšs datums = nav ierobežojuma). Beigusies/nākotnes/nenorādīta cena netiek piemērota
  un **neizdzēš** projektā jau esošu cenu. Cenas derīgums un avots tiek saglabāts projekta katalogā.
- **Kataloga mērvienība**, kas neatbilst projekta rindām ar to pašu artikulu, tiek izlaista (konversijas netiek izdomātas).
- **Priekšskatījums** (`preview_library`) piemēro bibliotēku projekta *kopijai* un rāda to pašu pārskatu, ko dos īstā piemērošana: jaunas / atjaunotas / nemainītas / izlaistas ar iemeslu.

## Statusi un trīs atšķirīgi veidi
| Veids (`kind`) | Nozīme | Apstrāde |
|---|---|---|
| `ģeometriska formula` | draiveris × norma | `apstiprināts` → rinda `approved`; `neapstiprināts` → `approved: false` |
| `vēsturisks koeficients` | fakts no iepriekšēja projekta | **vienmēr** `vēsturisks`; nekad netiek automātiski apstiprināts vai pārvērsts par validētu normu; pēc noklusējuma NETIEK piemērots, bet ar izvēles rūtiņu tiek pievienots kā neapstiprināts ar atzīmi «VĒSTURISKS (nav validēts)» |
| `komplekta budžets` | AD komplekts (viena summa/komplekts) | skat. zemāk; vienmēr `detail: komplekts` ar obligātu pieņēmumu |

## Draiveri (pamati)
Jau bijušie: `ext_net`, `int_one`, `int_both`, `roof`, `floor_net`, `floor_frame`, `ceiling`, `ext_len` (ārsienu garums = ēkas perimetrs), `int_len`, `win` (visi logi — nemainīts), `door`, `modules`, `direct`.
Pievienoti (Issue #20): `ext_gross`, `int_gross`, `roof_gross` (bruto laukumi), `facade_win` (logi ārsienās), `roof_win` (jumta logi — atsevišķi no fasādes), `rooms` un
`rooms_bed|living|kitchen|wet|tech|other` (telpu skaits pēc tipa; sadaļa «2c. Telpas un virtuves garums»), `kitchen_len` (virtuves garums, m). **Trūkstošs draiveris paliek neaprēķināts**
(rinda «nav ievadīts»), nulle netiek pieņemta.

## AD komplekti (standarts + klienta izvēles)
- Komplektam ir `levels` (piem., «standarta», «augstāks») un `default_level`. Piemērojot bibliotēku, tiek ielikts **standarta noklusējums**.
- Izvēle (`project["lib"]["kits"][kods]`): `enabled`, `level` (visam komplektam), `pos_levels` (atsevišķas pozīcijas aizstāšana ar citu līmeni), `pos_articles` (aizstāšana ar konkrētu artikulu),
  `skip` (pozīcijas izslēgšana), `add` (papildu pozīcijas: nosaukums, vienība, daudzums, artikuls).
- **Nedublēšana:** katram `lib_code` (`komplekts/pozīcija`) ir viena rinda; līmeņa maiņa to *aizstāj* (rindas `id` saglabājas); vairs nevajadzīgās rindas tiek dzēstas; viens artikuls komplektā netiek ielikts divreiz;
  komplekts tiek bloķēts, ja grupā jau ir lietotāja rinda, kas to sedz (`covers`, piem. «virtuve»); pozīcija ar `opening` (logi/durvis) netiek skaitīta, ja šīs atveres jau ir ievadītas kā atveres rindas.
- Cenas nāk no kataloga (`options` norāda artikulu; cena un tās derīgums — katalogā). Komplekta cena pa līmeņiem tiek rādīta sadaļā «0b»; ja kādai pozīcijai nav daudzuma vai cenas — «cena nav pilna».
- **Option List nav obligāts** AD stadijā; tā faila parsētājs netiek veidots (formāts nav zināms). PD/iepirkuma stadijā konkrēts modelis un artikuls tiek precizēts (aizstāšana ar artikulu).
- Komplekti nav MLK standarti: līmeņi, pozīcijas un cenas ir konfigurējami bibliotēkas failā.

## Aizsardzība pret dubultošanu ar konstrukciju slāņiem
- Piemērojot: grupu (grīda/ārsienas/iekšsienas/jumts/apdare) recepte, kuras nosaukums vai artikuls sakrīt ar projekta konstrukcijas slāni vai konstrukciju tipa recepti, tiek **izlaista** («dubultošana»).
- Aprēķinā: ja tāda bibliotēkas recepte tomēr nonāk projektā (piem., slānis pievienots vēlāk), `estimate()` atgriež kļūdu «Dubultošana: bibliotēkas recepte …» — tāme netiek uzskatīta par pilnu.
- Esošā lietotāja recepte ar to pašu grupu/nosaukumu/artikulu → bibliotēkas ieraksts netiek pievienots; darba operācija ar to pašu grupu/nosaukumu/posmu — tāpat.

## Prognoze un pārrēķins
Ģeometrijas, telpu, virtuves garuma vai komplektācijas maiņa pārrēķina tāmi un stundas. **Fiksētās AD prognozes versijas (`project["versions"]`) netiek mainītas.**
Bibliotēkas rindu manuāla labošana tabulā saglabā to izcelsmes atzīmi; atkārtota piemērošana tās atjauninās atbilstoši bibliotēkai (to rāda priekšskatījums kā «atjaunotas»).

## Ierobežojumi
Bibliotēkas rediģēšana lietotnē nav (fails tiek veidots ārpus lietotnes vai ģenerēts ar `tools/synthetic_library.py`). Komplekta līmeņu cenas tiek ņemtas no kataloga pēc artikula.
