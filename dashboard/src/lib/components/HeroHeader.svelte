<script lang="ts">
	import { fmt, fmtShort } from '$lib/utils';

	interface Props {
		title?: string;
		subtitle?: string;
		emoji?: string;
		metrics?: { label: string; value: number; icon?: string }[];
	}

	let { title = 'Synapse Community Dashboard', subtitle = 'Community engagement at a glance', emoji = '', metrics = [] }: Props = $props();
</script>

<header class="relative overflow-hidden rounded-2xl border border-brand-700/30 p-8 mb-8" style="background: linear-gradient(135deg, #1e0038, #3b0764, #13131a); background-size: 200% 200%; animation: gradientShift 8s ease infinite;">
	<!-- Animated decorative elements -->
	<div class="absolute inset-0 overflow-hidden pointer-events-none">
		<!-- Radial glow -->
		<div class="absolute -top-20 -right-20 w-80 h-80 rounded-full bg-brand-500/10 blur-3xl animate-pulse-slow"></div>
		<div class="absolute -bottom-20 -left-20 w-64 h-64 rounded-full bg-brand-600/8 blur-3xl animate-pulse-slow" style="animation-delay: 2s;"></div>
		<!-- Grid overlay -->
		<div class="absolute inset-0 opacity-[0.03]" style="background-image: linear-gradient(rgba(124,58,237,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(124,58,237,0.3) 1px, transparent 1px); background-size: 40px 40px;"></div>
	</div>

	<div class="relative z-10">
		<div class="flex items-center gap-3 mb-2">
			{#if emoji}<span class="text-3xl animate-float">{emoji}</span>{/if}
			<h1 class="text-3xl font-extrabold text-white tracking-tight text-glow-brand">{title}</h1>
		</div>
		<p class="text-zinc-400 text-lg max-w-xl">{subtitle}</p>

		{#if metrics.length > 0}
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
				{#each metrics as m, i}
					<div class="bg-white/5 backdrop-blur-sm rounded-xl px-4 py-3 border border-white/10 hover:bg-white/10 hover:border-brand-500/30 transition-all duration-200 hover:-translate-y-0.5" style="animation: fadeIn 0.4s ease-out {i * 0.1}s both;">
						<div class="flex items-center gap-2 mb-1">
							{#if m.icon}<span class="text-sm">{m.icon}</span>{/if}
							<p class="text-[10px] text-zinc-400 uppercase tracking-wider font-medium">{m.label}</p>
						</div>
						<p class="text-2xl font-bold text-white">{fmtShort(m.value)}</p>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</header>
