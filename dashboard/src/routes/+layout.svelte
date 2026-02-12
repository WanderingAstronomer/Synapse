<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import FlashMessage from '$lib/components/FlashMessage.svelte';
	import { auth } from '$lib/stores/auth';
	import { onMount } from 'svelte';

	let { children } = $props();
	let sidebarOpen = $state(false);

	onMount(() => {
		auth.init();
	});
</script>

<div class="flex min-h-screen">
	<Sidebar bind:open={sidebarOpen} />

	<div class="flex-1 lg:ml-0">
		<!-- Mobile topbar -->
		<div class="lg:hidden sticky top-0 z-20 bg-surface-50/80 backdrop-blur border-b border-surface-300 px-4 py-3 flex items-center gap-3">
			<button
				class="p-2 rounded-lg hover:bg-surface-200 transition-colors"
				onclick={() => (sidebarOpen = !sidebarOpen)}
				aria-label="Toggle sidebar"
			>
				<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
				</svg>
			</button>
			<span class="text-sm font-semibold text-zinc-200">⚡ Synapse</span>
		</div>

		<!-- Page content -->
		<main class="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
			{@render children()}
		</main>
	</div>
</div>

<FlashMessage />
