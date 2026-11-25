# Lokāla palaišana Windows 11

Šī palaišana ir paredzēta darbam **tikai uz jūsu datora**. PDF apstrāde notiek lokāli; lietotne klausās **tikai `127.0.0.1`**, telemetrija ir izslēgta, nav ārēja API, tunelēšanas vai publicēšanas.

## Priekšnosacījumi
- Windows 11.
- **Python 3.11 vai jaunāks** no python.org (instalētājā atzīmējiet "py launcher" vai "Add python.exe to PATH"). Prasība izriet no Streamlit 1.67 (`Requires-Python >=3.11`).
- Internets **tikai pirmajai instalēšanai** (atkarību pakotnes `requirements.txt` tiek lejupielādētas). Pēc tam PDF apstrādei internets nav vajadzīgs.
- Repozitorija mape (lejupielādēta kā ZIP vai ar Git). **Koda labot nav jāmaina.**

## Palaišana
1. Atveriet repozitorija mapi un divreiz noklikšķiniet **`start_mlk_windows.bat`**.
2. Pirmajā reizē skripts izveido mapi `.venv` un instalē atkarības (var ilgt dažas minūtes).
3. Pārlūkprogrammā atveras **http://127.0.0.1:8501**. Ja tā neatveras, atveriet šo adresi pats.
4. Apturēšana: aizveriet skripta logu vai nospiediet `Ctrl+C`.

Ja ports 8501 ir aizņemts, pirms palaišanas komandu logā iestatiet citu: `set MLK_PORT=8502` un tad palaidiet `start_mlk_windows.bat` no šī paša loga.

## Ko skripts dara
- pārbauda Python ≥ 3.11, izveido `.venv`, instalē **tikai** `requirements.txt`;
- palaiž `streamlit run app.py` ar `--server.address 127.0.0.1` un `--browser.gatherUsageStats false` (un vides mainīgo `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`);
- netiek mainīti publiskās lietotnes iestatījumi (`.streamlit/config.toml`).

`127.0.0.1` nozīmē, ka lietotne **nav pieejama citiem tīkla datoriem**. Windows ugunsmūris parasti neprasa atļauju, jo nav ienākošo savienojumu no tīkla.

## Ko NEdara
Neizmanto ārējus servisus, neveido publisku saiti, nepublicē PDF, nesūta statistiku. Konfidenciālus PDF **neievietojiet repozitorijā** (`.gitignore` ignorē `*.pdf`); lokālie pārskati tiek glabāti `local_reports\` (arī ignorēta).

## Kas ir faktiski testēts
- **Linux** (šīs izstrādes sesijas konteiners, Python 3.13, Streamlit 1.67.0, PyMuPDF 1.28.2): automātiski testi pārbauda `.bat` saturu (ASCII, CRLF, `127.0.0.1`, telemetrijas karodziņš, tikai `requirements.txt`), un reāls Streamlit process, palaists ar **tiem pašiem parametriem**, klausās tikai loopback adresē un atbild uz `/_stcore/health`.
- **Windows 11: `.bat` skripti šajā sesijā NAV izpildīti.** Tie ir uzrakstīti pēc standarta `cmd` sintakses un pārbaudīti tikai statiski. Pirmā palaišana uz Windows ir jāpārbauda lietotājam; ja radās kļūda, nokopējiet **komandu loga ziņojumu** (tas nesatur PDF saturu) un nosūtiet izstrādātājam.

## Problēmu risināšana
| Simptoms | Risinājums |
|---|---|
| "Python nav atrasts" | instalējiet Python 3.11+ no python.org ar "py launcher" |
| "nepieciešams Python 3.11" | instalējiet jaunāku Python versiju |
| neizdodas instalēt atkarības | pārbaudiet internetu (vajadzīgs tikai instalēšanai) un mēģiniet vēlreiz |
| ports aizņemts | `set MLK_PORT=8502` un palaidiet skriptu no tā paša loga |
| vēlaties pilnībā sākt no jauna | izdzēsiet mapi `.venv` un palaidiet skriptu vēlreiz |
