# Lokāla palaišana Windows 11

Šī palaišana ir paredzēta darbam **tikai uz jūsu datora**. PDF apstrāde notiek lokāli; lietotne klausās **tikai `127.0.0.1`**, telemetrija ir izslēgta, nav ārēja API, tunelēšanas vai publicēšanas.

## Priekšnosacījumi
- Windows 11.
- **Python 3.11 vai jaunāks** no python.org (instalētājā atzīmējiet "py launcher" vai "Add python.exe to PATH"). Prasība izriet no Streamlit 1.67 (`Requires-Python >=3.11`).
- Internets **tikai atkarību instalēšanai**: pirmajā palaišanā, pēc skaidri izvēlēta atjauninājuma (`start_mlk_windows.bat --update`) vai ja mainījies `requirements.txt` (piem., pēc koda atjaunināšanas). **Parastai atkārtotai palaišanai un PDF apstrādei internets nav vajadzīgs.**
- Repozitorija mape (lejupielādēta kā ZIP vai ar Git). **Koda labot nav jāmaina.**

## Palaišana
1. Atveriet repozitorija mapi un divreiz noklikšķiniet **`start_mlk_windows.bat`**.
2. Pirmajā reizē skripts izveido mapi `.venv` un instalē atkarības (var ilgt dažas minūtes; vajadzīgs internets). Nākamajās reizēs tas tikai pārbauda instalētās versijas (bez interneta) un palaiž lietotni uzreiz.
3. Pārlūkprogrammā atveras **http://127.0.0.1:8501**. Ja tā neatveras, atveriet šo adresi pats.
4. Apturēšana: aizveriet skripta logu vai nospiediet `Ctrl+C`.

**Atkarību atjaunināšana** (vajadzīgs internets): `start_mlk_windows.bat --update` komandu logā. Citādi atkarības tiek instalētas tikai tad, ja tās trūkst vai neatbilst `requirements.txt`.

Ja ports 8501 ir aizņemts, rīks pats izvēlas nākamo brīvo (8502 …) un parāda adresi. Citu sākuma portu var iestatīt ar `set MLK_PORT=8600` (tiek pārbaudīts: tikai cipari, 1024–65535).

## Ko skripts dara
`.bat` tikai atrod Python ≥ 3.11, izveido `.venv` un palaiž **fiksētu komandu** `.venv\Scripts\python.exe tools\local_setup.py start`. Visu pārējo dara šis Python palīgs (testējams, bez shell; ievade netiek likta komandrindā):
- pārbauda, vai instalētās pakotnes atbilst `requirements.txt` (**bez interneta**); `pip install -r requirements.txt` tiek palaists **tikai** ja trūkst/neatbilst vai ar `--update`;
- izvēlas portu (8501 vai nākamo brīvo) un palaiž `streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false` (+ `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`);
- netiek mainīti publiskās lietotnes iestatījumi (`.streamlit/config.toml`).

`127.0.0.1` nozīmē, ka lietotne **nav pieejama citiem tīkla datoriem**. Windows ugunsmūris parasti neprasa atļauju, jo nav ienākošo savienojumu no tīkla.

## Ko NEdara
Neizmanto ārējus servisus, neveido publisku saiti, nepublicē PDF, nesūta statistiku. Konfidenciālus PDF **neievietojiet repozitorijā** (`.gitignore` ignorē `*.pdf`); lokālie pārskati pēc noklusējuma tiek glabāti `%LOCALAPPDATA%\MLK_diagnostika` (ārpus sinhronizētām mapēm).

## Kas ir faktiski testēts
- **Linux** (šīs izstrādes sesijas konteiners, Python 3.13, Streamlit 1.67.0, PyMuPDF 1.28.2): automātiski testi pārbauda `.bat` saturu (ASCII, CRLF, fiksētas komandas bez lietotāja ievades komandrindā) un Python palīgu `tools/local_setup.py`; reāls Streamlit process, palaists ar šo palīgu, klausās tikai loopback adresē un atbild uz `/_stcore/health`; atkārtota palaišana **bez interneta** (atkarības netiek instalētas, `pip` netiek izsaukts, tīkla savienojumi testā bloķēti).
- **Windows 11: `.bat` skripti šajā sesijā NAV izpildīti.** Tie ir uzrakstīti pēc standarta `cmd` sintakses un pārbaudīti tikai statiski; visa loģika, kas var salūzt, ir pārcelta uz Python un testēta. Pirmā palaišana uz Windows ir jāpārbauda lietotājam; ja radās kļūda, nokopējiet **komandu loga ziņojumu** (tas nesatur PDF saturu) un nosūtiet izstrādātājam.

## Problēmu risināšana
| Simptoms | Risinājums |
|---|---|
| "Python nav atrasts" | instalējiet Python 3.11+ no python.org ar "py launcher" |
| "nepieciešams Python 3.11" | instalējiet jaunāku Python versiju |
| neizdodas instalēt atkarības | pārbaudiet internetu (vajadzīgs tikai instalēšanai) un mēģiniet vēlreiz |
| ports aizņemts | rīks pats izvēlas nākamo brīvo; adrese tiek parādīta |
| vēlaties atjaunināt atkarības | `start_mlk_windows.bat --update` (vajadzīgs internets) |
| vēlaties pilnībā sākt no jauna | izdzēsiet mapi `.venv` un palaidiet skriptu vēlreiz |
