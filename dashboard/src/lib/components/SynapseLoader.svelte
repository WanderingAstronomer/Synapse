<script lang="ts">
	interface Props {
		size?: 'sm' | 'md' | 'lg';
		text?: string;
	}

	let { size = 'md', text = '' }: Props = $props();

	const sizes = {
		sm: 'w-6 h-6',
		md: 'w-10 h-10',
		lg: 'w-16 h-16',
	};
</script>

<div class="flex flex-col items-center justify-center gap-3" role="status" aria-live="polite" aria-label={text || 'Loading'}>
	<!-- Synapse brain/node loader -->
	<div class="relative {sizes[size]}">
		<div class="absolute inset-0 rounded-full border-2 border-brand-500/20 animate-ping"></div>
		<div class="absolute inset-0 rounded-full border-2 border-brand-500/40"></div>
		<div class="absolute inset-1 rounded-full border-2 border-brand-400 border-t-transparent animate-spin"></div>
		<div class="absolute inset-0 flex items-center justify-center">
			<span class="text-brand-400 {size === 'lg' ? 'text-lg' : size === 'md' ? 'text-sm' : 'text-xs'}" aria-hidden="true">S</span>
		</div>
	</div>
	{#if text}
		<span class="text-xs text-zinc-500 animate-pulse">{text}</span>
	{/if}
</div>
