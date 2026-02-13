<script lang="ts">
	import { auth, isAdmin } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api } from '$lib/api';

	let { children } = $props();
	let checking = $state(true);
	let setupChecked = $state(false);

	// Use $effect instead of onMount to reactively track auth.loading.
	// This avoids the race condition where auth finishes loading before
	// the admin layout mounts, which left `checking` stuck as true.
	$effect(() => {
		let loading = false;
		const unsub = auth.loading.subscribe((v) => { loading = v; });
		unsub(); // read current value synchronously

		if (!loading) {
			checking = false;
			checkSetup();
		}
	});

	async function checkSetup() {
		// Skip setup gate if we're already on the setup page
		if ($page.url.pathname.startsWith('/admin/setup')) {
			setupChecked = true;
			return;
		}
		if (!$isAdmin) {
			setupChecked = true;
			return;
		}
		try {
			const status = await api.admin.getSetupStatus();
			if (!status.initialized) {
				setupChecked = true;
				goto('/admin/setup');
				return;
			}
		} catch {
			// If setup status fails, let admin through (endpoint may not exist yet)
		}
		setupChecked = true;
	}
</script>

{#if checking || !setupChecked}
	<div class="flex items-center justify-center h-64">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if !$isAdmin}
	<div class="flex flex-col items-center justify-center h-64 text-center">
		<span class="text-5xl mb-4">🔒</span>
		<h2 class="text-xl font-bold text-white mb-2">Admin Access Required</h2>
		<p class="text-sm text-zinc-500 mb-6 max-w-md">
			You need to sign in with a Discord account that has the admin role to access this section.
		</p>
		<a href="/api/auth/login" class="btn-primary">
			Sign in with Discord
		</a>
	</div>
{:else}
	{@render children()}
{/if}
