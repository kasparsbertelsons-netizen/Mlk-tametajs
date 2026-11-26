// Issue #18: mobilā (iPhone 13) pārbaude noklusējuma plūsmai līdz sintētiskai AD tāmei. PDF lejupielāde nav vajadzīga.
// Palaišana: streamlit run app.py --server.port 8765 --server.headless true  un  node tools/e2e_mobile_default_flow.js [url] [izvades_mape]
// Izmanto tikai sintētiskus datus. Nepieciešams: npm pakotne `playwright` (+ Chromium).
const { chromium, devices } = require('playwright');
const url = process.argv[2] || 'http://127.0.0.1:8765';
const out = process.argv[3] || '.';
const checks = [];
const check = (name, ok, extra = '') => { checks.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`); };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices['iPhone 13'] });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.getByText('Sākt: AD PDF vai demonstrācija').waitFor({ timeout: 60000 });

  const body = async () => await page.locator('body').innerText();
  const demo = page.getByRole('button', { name: /Ielādēt AD demonstrāciju/ });
  await demo.waitFor({ timeout: 60000 });
  await page.getByText('Gaida AD PDF').first().waitFor({ timeout: 60000 });
  let t = await body();
  check('1. noklusējuma skats = Pilnas ēkas AD tāme', await page.getByRole('radio', { name: 'Pilnas ēkas AD tāme' }).isChecked());
  check('2. versijas identifikators redzams', /Versija \S+ · commit/.test(t), (t.match(/Versija [^\n]+/) || [''])[0]);
  check('3. sākumā statuss «Gaida AD PDF» un nākamā darbība', /Gaida AD PDF/.test(t) && /Nākamā darbība/.test(t));
  check('4. AD demo poga redzama bez izvēlnēm', await demo.isVisible());
  check('5. PDF augšupielāde redzama bez izvēršanas', await page.locator('[data-testid="stFileUploader"]').first().isVisible());
  await page.screenshot({ path: `${out}/01_start.png`, fullPage: false });

  await demo.click();
  await page.getByText('AD demonstrācija ielādēta').first().waitFor({ timeout: 60000 });
  await page.getByText('Tāmes rezultāts').first().waitFor({ timeout: 60000 });
  await page.getByText('Pārdošanas cena bez PVN').first().waitFor({ timeout: 60000 });
  t = await body();
  check('6. pēc demo: statuss «AD demonstrācija ielādēta» + nākamā darbība', /AD demonstrācija ielādēta/.test(t) && /Nākamā darbība/.test(t));
  check('7. tāmes rezultāts un kopsummas redzamas', /Tāmes rezultāts/.test(t) && /EUR/.test(t));
  check('8. sintētiskā AD demo kontroles summas redzamas: pašizmaksa 100973.20, pārdošanas cena bez PVN 116119.18', /100973\.20 EUR/.test(t) && /116119\.18 EUR/.test(t));
  await page.getByText('Tāmes rezultāts').first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${out}/02_result.png`, fullPage: false });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check('9. nav horizontālas lapas ritināšanas (mobilais)', overflow <= 1, `pārpalikums ${overflow}px`);

  // Vecie režīmi saglabāti
  await page.getByText('Vecais AD: tikai grīdas rāmis').first().click();
  await page.getByText('Vecais režīms: tikai grīdas rāmis').first().waitFor({ timeout: 60000 });
  check('10. vecais AD režīms atveras', true);
  await page.getByText('PD: līmsiju specifikācija').first().click();
  await page.getByText('PD: līmsiju specifikācijas nolasīšana no PDF').first().waitFor({ timeout: 60000 });
  check('11. PD režīms atveras', true);

  // 2. scenārijs: sintētiska AD PDF augšupielāde (samples/ad_building) → kandidāti → «droši» → pārnese → tāme
  const page2 = await ctx.newPage();
  await page2.goto(url, { waitUntil: 'networkidle' });
  await page2.getByText('Gaida AD PDF').first().waitFor({ timeout: 60000 });
  await page2.locator('input[type="file"]').first().setInputFiles(require('path').join(__dirname, '..', 'samples', 'ad_building', 'AD_sintetiska_eka.pdf'));
  await page2.getByText(/atrasti \d+ kandidāti/).first().waitFor({ timeout: 90000 });
  check('13. PDF augšupielāde: statuss ar kandidātu skaitu', true, (await page2.getByText(/atrasti \d+ kandidāti/).first().innerText()));
  await page2.screenshot({ path: `${out}/03_pdf_result.png` });
  await page2.getByRole('button', { name: /Atzīmēt visus droši nolasāmos/ }).click();
  await page2.getByRole('button', { name: /Pārnest apstiprinātos uz tāmi/ }).click();
  await page2.getByText('Apstiprinātie kandidāti pārnesti uz tāmi').or(page2.getByText(/Pārnesti \d+ kandidāti/)).first().waitFor({ timeout: 90000 });
  check('14. pēc pārneses redzams paziņojums un tāmes rezultāts', await page2.getByText('Tāmes rezultāts').first().isVisible());
  await page2.screenshot({ path: `${out}/04_pdf_applied.png` });
  check('15. lapas JS kļūdu nav', errors.length === 0, errors.join(' | '));
  await browser.close();
  const failed = checks.filter(x => !x).length;
  console.log(failed ? `KOPĀ: ${failed} NEIZDEVĀS` : `KOPĀ: visas ${checks.length} pārbaudes izdevās`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
