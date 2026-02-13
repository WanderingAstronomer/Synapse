import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

let adapter;
try {
	adapter = (await import('@sveltejs/adapter-node')).default;
} catch {
	adapter = () => ({
		name: 'adapter-missing',
		adapt: async () => {}
	});
}

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
