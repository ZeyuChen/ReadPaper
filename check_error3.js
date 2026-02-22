const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ headless: "new" });
    const page = await browser.newPage();

    // Inject error listener before navigation
    await page.evaluateOnNewDocument(() => {
        window.addEventListener('error', e => {
            console.log('CRITICAL_WINDOW_ERROR:', e.message, e.error?.stack);
        });
        window.addEventListener('unhandledrejection', e => {
            console.log('CRITICAL_PROMISE_REJECTION:', e.reason);
        });
    });

    page.on('console', msg => {
        // Print arguments safely
        const argsText = msg.args().map(a => a.toString()).join(' ');
        console.log(`[CONSOLE_${msg.type().toUpperCase()}] ${msg.text()} | args: ${argsText}`);
    });

    try {
        await page.goto('https://readpaper-frontend-989182646968.us-central1.run.app', { waitUntil: 'networkidle2', timeout: 30000 });
        await new Promise(resolve => setTimeout(resolve, 5000));
    } catch (e) {
        console.error(`Navigation Error: ${e}`);
    }

    await browser.close();
})();
