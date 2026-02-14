<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth.svelte';
	import { flash } from '$lib/stores/flash.svelte';

	let verifying = $state(true);

	onMount(async () => {
		const params = $page.url.searchParams;
		const token = params.get('token');
		const code = params.get('code');
		const state = params.get('state');
		const error = params.get('auth_error');

		if (error) {
			flash.error(error === 'not_admin' ? 'Your Discord account does not have the admin role.' : error);
			goto('/');
			return;
		}

		if (token) {
			// Verify token server-side before granting access
			const user = await auth.login(token);
			if (user) {
				flash.success('Signed in as admin');
				goto('/admin/setup');
			} else {
				flash.error('Authentication failed — token could not be verified.');
				goto('/');
			}
		} else if (code && state) {
			const callbackUrl = `/api/auth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;
			window.location.assign(callbackUrl);
		} else {
			flash.error('No authentication token received');
			goto('/');
		}

		verifying = false;
	});
</script>

<div class="flex items-center justify-center h-64">
	<div class="text-center">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
		<p class="text-sm text-zinc-400">{verifying ? 'Verifying credentials…' : 'Redirecting…'}</p>
	</div>
</div>
