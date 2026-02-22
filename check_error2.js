const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ headless: "new" });
    const page = await browser.newPage();

    page.on('console', msg => {
        console.log(`[CONSOLE_${msg.type().toUpperCase()}] ${msg.text()}`);
    });

    page.on('pageerror', error => {
        console.error(`[PAGE_ERROR] ${error.message}`);
    });

    console.log("Navigating to https://readpaper-frontend-989182646968.us-central1.run.app ...");
    try {
        await page.goto('https://readpaper-frontend-989182646968.us-central1.run.app', { waitUntil: 'networkidle0', timeout: 30000 });
        await new Promise(resolve => setTimeout(resolve, 5000));
    } catch (e) {
        console.error(`Navigation Error: ${e}`);
    }

    await browser.close();
})();
