<script lang="ts">
	import { auth, isAdmin } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	let { children } = $props();
	let checking = $state(true);

	onMount(() => {
		// Wait for auth to finish loading, then check
		const unsub = auth.loading.subscribe((loading) => {
			if (!loading) {
				checking = false;
				unsub();
			}
		});
	});
</script>

{#if checking}
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
