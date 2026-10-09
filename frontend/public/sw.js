/*
 * Lead Gen service worker — installability and a graceful offline screen only.
 *
 * Served at /sw.js by Django (debt_project/urls.py) and registered with scope
 * /lead-gen. It deliberately uses NO Cache Storage: case data, credit reports,
 * API responses, tokens and app files are never stored by this worker.
 *
 * Only top-level page navigations are handled; every other request (/api,
 * /static, fonts, ...) is left to the browser untouched. When a navigation
 * fails because the device is offline, a small built-in page is shown instead
 * of the browser's error page.
 */

const OFFLINE_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lead Gen Check — offline</title>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         font-family: Inter, system-ui, sans-serif; background: #f8fafc; color: #0f172a; }
  main { max-width: 22rem; padding: 2rem 1.5rem; text-align: center; }
  h1 { font-size: 1.05rem; margin: 0 0 .5rem; }
  p { font-size: .9rem; color: #475569; margin: 0 0 1.25rem; }
  button { font: inherit; font-size: .9rem; font-weight: 600; padding: .6rem 1.1rem; border-radius: .375rem;
           border: 0; background: #112238; color: #fff; cursor: pointer; }
</style>
</head>
<body>
<main>
  <h1>You're offline</h1>
  <p>The Lead Gen check needs a connection to work. Reconnect, then try again.</p>
  <button type="button" onclick="location.reload()">Try again</button>
</main>
</body>
</html>`

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.mode !== 'navigate' || request.method !== 'GET') return
  event.respondWith(
    fetch(request).catch(() => new Response(OFFLINE_HTML, {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
    })),
  )
})
