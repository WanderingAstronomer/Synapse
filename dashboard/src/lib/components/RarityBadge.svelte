<script lang="ts">
	interface Props {
		rarity: string;
		label?: string;
		color?: string;
		size?: 'sm' | 'md';
	}

	let { rarity, label, color, size = 'sm' }: Props = $props();

	const RARITY_STYLES: Record<string, { bg: string; text: string; border: string; glow: string }> = {
		common:    { bg: 'bg-zinc-500/10',   text: 'text-zinc-400',   border: 'border-zinc-500/20', glow: '' },
		uncommon:  { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20', glow: '' },
		rare:      { bg: 'bg-blue-500/10',   text: 'text-blue-400',   border: 'border-blue-500/20', glow: 'shadow-sm shadow-blue-500/20' },
		epic:      { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', glow: 'shadow-sm shadow-purple-500/30' },
		legendary: { bg: 'bg-amber-500/15',  text: 'text-amber-400',  border: 'border-amber-500/40', glow: 'shadow-sm shadow-amber-500/30 animate-pulse-slow' },
	};

	const RARITY_ICONS: Record<string, string> = {
		common: '●',
		uncommon: '◆',
		rare: '★',
		epic: '✦',
		legendary: '✧',
	};

	const style = $derived(RARITY_STYLES[rarity] ?? RARITY_STYLES.common);
	const displayLabel = $derived(label ?? rarity.charAt(0).toUpperCase() + rarity.slice(1));
	const icon = $derived(RARITY_ICONS[rarity] ?? '●');
</script>

<span class="badge {style.bg} {style.text} border {style.border} {style.glow} {size === 'md' ? 'px-3 py-1 text-sm' : ''}">
	<span class="text-[10px]">{icon}</span>
	{displayLabel}
</span>
