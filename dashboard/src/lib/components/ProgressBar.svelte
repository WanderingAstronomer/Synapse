<script lang="ts">
	interface Props {
		value: number;   /** 0 to 1 */
		height?: number; /** px */
		color?: string;  /** Tailwind bg class */
		label?: string;
		showPct?: boolean;
	}

	let { value, height = 8, color = 'bg-brand-500', label = '', showPct = false }: Props = $props();

	const pct = $derived(Math.min(Math.max(value * 100, 0), 100));
</script>

<div class="w-full">
	{#if label || showPct}
		<div class="flex justify-between items-center mb-1">
			{#if label}<span class="text-xs text-zinc-400">{label}</span>{/if}
			{#if showPct}<span class="text-xs text-zinc-500 font-mono">{pct.toFixed(0)}%</span>{/if}
		</div>
	{/if}
	<div class="w-full bg-surface-300 rounded-full overflow-hidden" style="height: {height}px">
		<div
			class="{color} rounded-full transition-all duration-500 ease-out"
			style="width: {pct}%; height: 100%"
		></div>
	</div>
</div>
