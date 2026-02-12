<script lang="ts">
	import { flash } from '$lib/stores/flash';
	import { fly } from 'svelte/transition';

	const TYPE_STYLES = {
		success: 'bg-green-500/10 border-green-500/30 text-green-400',
		error:   'bg-red-500/10 border-red-500/30 text-red-400',
		info:    'bg-blue-500/10 border-blue-500/30 text-blue-400',
		warning: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
	};

	const TYPE_ICONS = {
		success: '✓',
		error:   '✕',
		info:    'ℹ',
		warning: '⚠',
	};
</script>

{#if $flash.length > 0}
	<div class="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
		{#each $flash as msg (msg.id)}
			<div
				class="flex items-start gap-3 px-4 py-3 rounded-lg border {TYPE_STYLES[msg.type]} shadow-xl backdrop-blur"
				transition:fly={{ x: 100, duration: 200 }}
			>
				<span class="text-lg font-bold leading-none mt-0.5">{TYPE_ICONS[msg.type]}</span>
				<p class="text-sm flex-1">{msg.message}</p>
				<button
					class="text-zinc-500 hover:text-zinc-300 text-lg leading-none"
					onclick={() => flash.dismiss(msg.id)}
				>×</button>
			</div>
		{/each}
	</div>
{/if}
