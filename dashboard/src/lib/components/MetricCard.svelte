<script lang="ts">
	import { fmtShort } from '$lib/utils';

	interface Props {
		label: string;
		value: number;
		icon?: string;
		trend?: number | null;
		color?: 'brand' | 'gold' | 'green' | 'blue' | 'pink';
	}

	let { label, value, icon = '', trend = null, color = 'brand' }: Props = $props();

	const ringColors = {
		brand: 'ring-brand-500/20',
		gold: 'ring-gold-500/20',
		green: 'ring-green-500/20',
		blue: 'ring-blue-500/20',
		pink: 'ring-pink-500/20',
	};

	const iconBgs = {
		brand: 'bg-brand-500/10 text-brand-400',
		gold: 'bg-gold-500/10 text-gold-400',
		green: 'bg-green-500/10 text-green-400',
		blue: 'bg-blue-500/10 text-blue-400',
		pink: 'bg-pink-500/10 text-pink-400',
	};
</script>

<div class="card card-hover ring-1 {ringColors[color]} animate-fade-in group cursor-default">
	<div class="flex items-start justify-between">
		<div>
			<p class="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</p>
			<p class="text-3xl font-bold text-white mt-2">{fmtShort(value)}</p>
			{#if trend !== null}
				<p class="text-xs mt-1 {trend >= 0 ? 'text-green-400' : 'text-red-400'}">
					{trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}%
				</p>
			{/if}
		</div>
		{#if icon}
		<div class="w-10 h-10 rounded-xl flex items-center justify-center text-lg {iconBgs[color]} transition-transform duration-300 group-hover:scale-110">
			{icon}
		</div>
		{/if}
	</div>
</div>
