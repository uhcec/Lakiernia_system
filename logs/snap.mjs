const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

  // inject token so ProtectedRoute passes
  await page.goto("http://127.0.0.1:5173");
  await page.evaluate(() => {
    localStorage.setItem("auth_token", arguments[0]);
  }, "dummy");

  // login properly
  await page.goto("http://127.0.0.1:5173/login");
  await page.fill('input[type="text"], input[name="login"], input[placeholder*="login"], input[placeholder*="Login"], input[id*="login"]', "biuro");
  await page.fill('input[type="password"]', "bi1");
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1500);
  await page.goto("http://127.0.0.1:5173/zlecenia");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: "C:/Users/admin/Desktop/Lakiernia_system/logs/screenshot_zlecenia.png", fullPage: false });
  await browser.close();
  console.log("done");
})();
