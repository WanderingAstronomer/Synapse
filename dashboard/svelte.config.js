import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import adapterNode from '@sveltejs/adapter-node';

// adapter-node is required because this dashboard uses a server-side API proxy
// route (src/routes/api/[...path]/+server.ts) that forwards requests to the
// FastAPI backend.  adapter-static cannot execute server routes.
// SSR itself is disabled (ssr = false in +layout.ts) — the Node server only
// serves the static SPA bundle and handles the /api proxy.
const adapter = adapterNode;

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({ out: 'build' }),
		alias: {
			$lib: 'src/lib'
		},
		version: {
			// Auto-detect app updates after Docker rebuilds.
			// SvelteKit compares this at build time; when the client detects
			// a mismatch it can trigger a full navigation instead of a 404.
			pollInterval: 60000
		}
	}
};

export default config;
