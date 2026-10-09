const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  
  await page.goto("http://127.0.0.1:5173/login");
  await page.waitForLoadState("networkidle");
  await page.fill("input[type='text']", "biuro");
  await page.fill("input[type='password']", "bi1");
  await page.click("button[type='submit']");
  await page.waitForTimeout(2000);
  
  await page.goto("http://127.0.0.1:5173/zlecenia");
  await page.waitForTimeout(2500);
  
  // Screenshot INTAKE tab (default)
  await page.screenshot({ path: "shot_intake.png" });
  
  // Click Na produkcji tab
  await page.click("button:has-text('Na produkcji')");
  await page.waitForTimeout(800);
  await page.screenshot({ path: "shot_production.png" });
  
  // Click Gotowe tab
  await page.click("button:has-text('Gotowe')");
  await page.waitForTimeout(800);
  await page.screenshot({ path: "shot_ready.png" });
  
  await browser.close();
  console.log("done");
})();
