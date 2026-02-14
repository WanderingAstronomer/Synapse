<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import FlashMessage from '$lib/components/FlashMessage.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import { siteSettings } from '$lib/stores/siteSettings.svelte';
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { updated } from '$app/stores';
	import { beforeNavigate } from '$app/navigation';

	let { children } = $props();

	let sidebar: Sidebar;

	/** Load favicon from public settings. */
	function applyFavicon(url: string | null) {
		let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
		if (!url) {
			// Set a default emoji favicon via SVG data URI
			if (!link) {
				link = document.createElement('link');
				link.rel = 'icon';
				document.head.appendChild(link);
			}
			link.href = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>";
			return;
		}
		if (!link) {
			link = document.createElement('link');
			link.rel = 'icon';
			document.head.appendChild(link);
		}
		link.href = url;
	}

	onMount(() => {
		auth.init();
		currency.init();
		// Load public settings (page titles, favicon, etc.)
		siteSettings.init().then((settings) => {
			applyFavicon((settings['display.favicon_url'] as string) || null);
		});
	});

	// If SvelteKit detects a version mismatch (e.g. after a Docker rebuild),
	// force a full page reload on the next navigation so the browser picks up
	// the new JS bundles instead of 404-ing on stale chunk hashes.
	beforeNavigate(({ willUnload, to }) => {
		if ($updated && !willUnload && to?.url) {
			location.href = to.url.href;
		}
	});
</script>

<div class="flex min-h-screen">
	<!-- Skip to main content link — visible only on keyboard focus -->
	<a
		href="#main-content"
		class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-brand-600 focus:text-white focus:text-sm focus:font-medium focus:shadow-lg"
	>
		Skip to main content
	</a>

	<Sidebar bind:this={sidebar} />

	<div class="flex-1 min-w-0 overflow-x-hidden">
		<!-- Mobile header with hamburger -->
		<header class="mobile-header">
			<button
				class="p-2 -ml-1 rounded-lg text-zinc-400 hover:text-white hover:bg-surface-200 transition-colors"
				onclick={() => sidebar.open()}
				aria-label="Open sidebar menu"
			>
				<svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
				</svg>
			</button>
			<span class="text-lg font-bold text-white tracking-tight">Synapse</span>
			<div class="w-10"></div><!-- spacer for centering -->
		</header>

		<!-- Page content -->
		<main id="main-content" class="p-4 lg:p-8">
			{@render children()}
		</main>
	</div>
</div>

<FlashMessage />
