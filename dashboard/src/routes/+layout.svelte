<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import FlashMessage from '$lib/components/FlashMessage.svelte';
	import { auth } from '$lib/stores/auth';
	import { currencyLabels } from '$lib/stores/currency';
	import { onMount } from 'svelte';
	import { updated } from '$app/stores';
	import { beforeNavigate } from '$app/navigation';

	let { children } = $props();

	onMount(() => {
		auth.init();
		currencyLabels.init();
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
	<Sidebar />

	<div class="flex-1 min-w-0 overflow-x-hidden">
		<!-- Page content -->
		<main class="p-8">
			{@render children()}
		</main>
	</div>
</div>

<FlashMessage />
