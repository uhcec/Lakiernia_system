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
  
  console.log("URL after login:", page.url());
  await page.goto("http://127.0.0.1:5173/zlecenia");
  await page.waitForTimeout(2000);
  
  await page.screenshot({ path: "C:/Users/admin/Desktop/Lakiernia_system/logs/shot_zlecenia.png" });
  await browser.close();
  console.log("done");
})();
