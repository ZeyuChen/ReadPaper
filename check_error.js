const puppeteer = require('puppeteer');

(async () => {
    console.log("Launching browser...");
    const browser = await puppeteer.launch({ headless: "new" });
    const page = await browser.newPage();

    page.on('console', msg => {
        if (msg.type() === 'error') {
            console.error(`[Browser Console Error]: ${msg.text()}`);
        }
    });

    page.on('pageerror', error => {
        console.error(`[Browser Page Error]: ${error.message}`);
    });

    console.log("Navigating to https://readpaper-frontend-989182646968.us-central1.run.app ...");
    try {
        await page.goto('https://readpaper-frontend-989182646968.us-central1.run.app', { waitUntil: 'networkidle0', timeout: 30000 });
        console.log("Page loaded. Waiting 3 seconds for client-side React to throw...");
        await new Promise(resolve => setTimeout(resolve, 3000));
    } catch (e) {
        console.error(`Navigation Error: ${e}`);
    }

    await browser.close();
})();
