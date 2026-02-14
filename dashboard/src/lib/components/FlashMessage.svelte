<script lang="ts">
	import { flash } from '$lib/stores/flash.svelte';
	import { fly } from 'svelte/transition';
	import { FLASH_CONFIG } from '$lib/constants';
</script>

{#if flash.messages.length > 0}
	<div class="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
		{#each flash.messages as msg (msg.id)}
			<div
				class="flex items-start gap-3 px-4 py-3 rounded-lg border {FLASH_CONFIG[msg.type]?.styles || ''} shadow-xl backdrop-blur"
				transition:fly={{ x: 100, duration: 200 }}
			>
				<span class="text-lg font-bold leading-none mt-0.5">{FLASH_CONFIG[msg.type]?.icon || 'ℹ'}</span>
				<p class="text-sm flex-1">{msg.message}</p>
				<button
					class="text-zinc-500 hover:text-zinc-300 text-lg leading-none"
					onclick={() => flash.dismiss(msg.id)}
				>×</button>
			</div>
		{/each}
	</div>
{/if}
