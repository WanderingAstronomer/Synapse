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
		}
	}
};

export default config;
