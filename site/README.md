# Heritage Kitchen frontend

The German interface uses SvelteKit and Svelte 5. The static adapter builds a
single-page app. The PWA manifest lives in `static/`, the service worker in
`src/service-worker.js`, and offline data handling in `src/lib/offline/`.

## Develop

Use Node.js 24.15.0 or newer and run these commands from `site/`.

```sh
npm ci
npm run dev
```

Run the backend at `http://127.0.0.1:8000`. Vite proxies `/api` and `/media`
to it. For backend setup, see the [main README](../README.md#development).

## Check and build

```sh
npm run check
npm test
npm run build
```

The test script runs Node logic tests and Vitest component tests. Use
`npm run test:ui` for the component suite. The build goes into `build/`.
Use `npm run preview` to serve it locally. In Docker the FastAPI app serves
the built files.

Shared styles and design tokens live in `src/app.css`. Font and icon
attribution is in [licenses/](licenses/README.md).
