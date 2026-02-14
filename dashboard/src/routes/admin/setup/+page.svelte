<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	// Setup has been consolidated under the Settings view.
	// Redirect for backward compatibility.
	onMount(() => {
		goto('/admin/settings?tab=setup', { replaceState: true });
	});
</script>

<div class="flex items-center justify-center h-48">
	<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
</div>
