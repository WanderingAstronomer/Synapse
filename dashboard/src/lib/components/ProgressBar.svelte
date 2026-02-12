<script lang="ts">
	interface Props {
		value: number;   /** 0 to 1 */
		height?: number; /** px */
		color?: string;  /** Tailwind bg class */
		label?: string;
		showPct?: boolean;
		glow?: boolean;
		segments?: number;
	}

	let { value, height = 8, color = 'bg-brand-500', label = '', showPct = false, glow = false, segments = 0 }: Props = $props();

	const pct = $derived(Math.min(Math.max(value * 100, 0), 100));
</script>

<div class="w-full">
	{#if label || showPct}
		<div class="flex justify-between items-center mb-1">
			{#if label}<span class="text-xs text-zinc-400">{label}</span>{/if}
			{#if showPct}<span class="text-xs text-zinc-500 font-mono">{pct.toFixed(0)}%</span>{/if}
		</div>
	{/if}
	<div class="relative w-full bg-surface-300 rounded-full overflow-hidden" style="height: {height}px">
		<!-- Filled bar -->
		<div
			class="{color} rounded-full transition-all duration-700 ease-out"
			style="width: {pct}%; height: 100%;"
		></div>
		<!-- Glow effect for high progress -->
		{#if glow && pct > 50}
			<div
				class="absolute top-0 left-0 h-full rounded-full opacity-40 blur-sm {color}"
				style="width: {pct}%;"
			></div>
		{/if}
		<!-- Segment lines -->
		{#if segments > 0}
			{#each Array(segments - 1) as _, i}
				<div
					class="absolute top-0 w-px bg-surface-0/40"
					style="left: {((i + 1) / segments) * 100}%; height: 100%;"
				></div>
			{/each}
		{/if}
	</div>
</div>
