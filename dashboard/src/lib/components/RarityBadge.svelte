<script lang="ts">
	interface Props {
		rarity: string;
		label?: string;
		color?: string;
	}

	let { rarity, label, color }: Props = $props();

	const RARITY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
		common:    { bg: 'bg-zinc-500/10',  text: 'text-zinc-400',   border: 'border-zinc-500/20' },
		uncommon:  { bg: 'bg-green-500/10', text: 'text-green-400',  border: 'border-green-500/20' },
		rare:      { bg: 'bg-blue-500/10',  text: 'text-blue-400',   border: 'border-blue-500/20' },
		epic:      { bg: 'bg-purple-500/10',text: 'text-purple-400', border: 'border-purple-500/20' },
		legendary: { bg: 'bg-amber-500/10', text: 'text-amber-400',  border: 'border-amber-500/20' },
	};

	const style = $derived(RARITY_STYLES[rarity] ?? RARITY_STYLES.common);
	const displayLabel = $derived(label ?? rarity.charAt(0).toUpperCase() + rarity.slice(1));
</script>

<span class="badge {style.bg} {style.text} border {style.border}">
	{#if color}
		<span class="w-2 h-2 rounded-full" style="background-color: {color}"></span>
	{/if}
	{displayLabel}
</span>
