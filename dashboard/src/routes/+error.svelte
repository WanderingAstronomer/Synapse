<script lang="ts">
	import { page } from '$app/stores';
</script>

<div class="flex flex-col items-center justify-center h-64 text-center px-4">
	<h2 class="text-xl font-bold text-white mb-2">Something went wrong</h2>
	<p class="text-sm text-zinc-400 mb-2 max-w-md">
		{$page.error?.message || 'An unexpected error occurred.'}
	</p>
	<p class="text-xs text-zinc-600 mb-6">
		Status: {$page.status} &middot; URL: {$page.url.pathname}
	</p>
	<div class="flex gap-3">
		<button class="btn-primary text-sm" onclick={() => window.location.reload()}>
			Refresh Page
		</button>
		<a href="/" class="btn-secondary text-sm">Go Home</a>
	</div>
</div>
