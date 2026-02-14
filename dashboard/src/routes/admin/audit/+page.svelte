<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	// Audit log has been consolidated under the Logs view.
	// Redirect for backward compatibility.
	onMount(() => {
		goto('/admin/logs?tab=audit', { replaceState: true });
	});
</script>

<div class="flex items-center justify-center h-48">
	<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
</div>
