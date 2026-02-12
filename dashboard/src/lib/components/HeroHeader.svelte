<script lang="ts">
	import { fmt, fmtShort } from '$lib/utils';

	interface Props {
		title?: string;
		subtitle?: string;
		emoji?: string;
		metrics?: { label: string; value: number; icon?: string }[];
	}

	let { title = 'Synapse Club Pulse', subtitle = 'Community engagement at a glance', emoji = '⚡', metrics = [] }: Props = $props();
</script>

<header class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-900 via-brand-800 to-surface-100 border border-brand-700/30 p-8 mb-8">
	<!-- Decorative dots -->
	<div class="absolute top-0 right-0 w-64 h-64 opacity-5">
		<svg viewBox="0 0 200 200" fill="currentColor" class="text-brand-300">
			{#each Array(10) as _, i}
				{#each Array(10) as _, j}
					<circle cx={i * 20 + 10} cy={j * 20 + 10} r="2" />
				{/each}
			{/each}
		</svg>
	</div>

	<div class="relative z-10">
		<div class="flex items-center gap-3 mb-2">
			<span class="text-3xl">{emoji}</span>
			<h1 class="text-3xl font-extrabold text-white tracking-tight">{title}</h1>
		</div>
		<p class="text-zinc-400 text-lg max-w-xl">{subtitle}</p>

		{#if metrics.length > 0}
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
				{#each metrics as m}
					<div class="bg-white/5 backdrop-blur rounded-xl px-4 py-3 border border-white/10">
						<p class="text-xs text-zinc-400 uppercase tracking-wider">{m.label}</p>
						<p class="text-2xl font-bold text-white mt-1">{fmtShort(m.value)}</p>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</header>
