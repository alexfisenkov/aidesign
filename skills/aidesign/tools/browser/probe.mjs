// Проверка браузерного модуля: какой браузер запускается и с каким User-Agent.
import { main, loadPlaywright, launch, honestAgent } from './common.mjs';

main(async () => {
  const pw = loadPlaywright();
  const { browser, name, tried } = await launch(pw);
  try {
    return { ok: true, browser: name, version: browser.version(), userAgent: await honestAgent(browser), tried };
  } finally {
    await browser.close();
  }
});
