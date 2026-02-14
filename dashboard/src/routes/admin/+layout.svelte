<script lang="ts">
	import { auth } from '$lib/stores/auth.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api } from '$lib/api';

	let { children } = $props();
	let checking = $state(true);
	let setupNeeded = $state(false);

	// Unblock the guard whenever auth finishes loading.
	$effect(() => {
		if (!auth.loading) {
			checking = false;
			checkSetup();
		}
	});

	async function checkSetup() {
		if (!auth.isAdmin) return;
		try {
			const status = await api.admin.getSetupStatus();
			setupNeeded = !status.initialized;
		} catch {
			// If setup status fails, assume OK
		}
	}
</script>

{#if checking}
	<div class="flex items-center justify-center h-64">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if !auth.isAdmin}
	<div class="flex flex-col items-center justify-center h-64 text-center">
		
		<h2 class="text-xl font-bold text-white mb-2">Admin Access Required</h2>
		<p class="text-sm text-zinc-500 mb-6 max-w-md">
			You need to sign in with a Discord account that has the admin role to access this section.
		</p>
		<a href="/api/auth/login" class="btn-primary">
			Sign in with Discord
		</a>
	</div>
{:else}
	{#if setupNeeded}
		<div class="mx-8 mt-6 mb-0 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-between">
			<div class="flex items-center gap-3">
				<span class="text-amber-400 text-lg">⚠</span>
				<div>
					<p class="text-sm font-medium text-amber-200">Setup not complete</p>
					<p class="text-xs text-amber-400/70">Run the bootstrap to initialize layouts, seasons, and channel sync.</p>
				</div>
			</div>
			<a href="/admin/settings?tab=setup" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 transition-colors">
				Go to Setup
			</a>
		</div>
	{/if}
	{@render children()}
{/if}
