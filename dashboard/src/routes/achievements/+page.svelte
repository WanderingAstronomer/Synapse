<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Achievement, type RecentAchievement } from '$lib/api';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { fmt, timeAgo, capitalize } from '$lib/utils';

	let achievements = $state<Achievement[]>([]);
	let recent = $state<RecentAchievement[]>([]);
	let loading = $state(true);
	let categoryFilter = $state('');
	let rarityFilter = $state('');

	onMount(async () => {
		try {
			const [achRes, recRes] = await Promise.all([
				api.getAchievements(),
				api.getRecentAchievements(10),
			]);
			achievements = achRes.achievements;
			recent = recRes.recent;
		} catch (e) {
			console.error('Achievements load failed:', e);
		} finally {
			loading = false;
		}
	});

	const categories = $derived([...new Set(achievements.map((a) => a.category))].sort());
	const rarities = $derived([...new Set(achievements.map((a) => a.rarity))]);

	const filtered = $derived(
		achievements.filter((a) => {
			if (categoryFilter && a.category !== categoryFilter) return false;
			if (rarityFilter && a.rarity !== rarityFilter) return false;
			return true;
		})
	);

	const RARITY_GLOW: Record<string, string> = {
		legendary: 'shadow-amber-500/20 border-amber-500/30',
		epic: 'shadow-purple-500/20 border-purple-500/30',
		rare: 'shadow-blue-500/20 border-blue-500/30',
		uncommon: 'shadow-green-500/20 border-green-500/30',
		common: '',
	};
</script>

<svelte:head><title>Achievements — Synapse</title></svelte:head>

<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">Achievements</h1>
	<p class="text-sm text-zinc-500 mt-1">Collect badges, earn rewards, show off your dedication.</p>
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else}
	<!-- Filters -->
	<div class="flex flex-wrap gap-2 mb-6">
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{!categoryFilter ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => (categoryFilter = '')}
		>
			All Categories
		</button>
		{#each categories as cat}
			<button
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
					{categoryFilter === cat ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
				onclick={() => (categoryFilter = cat)}
			>
				{capitalize(cat)}
			</button>
		{/each}
		<div class="w-px bg-surface-400 mx-1"></div>
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{!rarityFilter ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => (rarityFilter = '')}
		>
			All Rarities
		</button>
		{#each rarities as rar}
			<button
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
					{rarityFilter === rar ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
				onclick={() => (rarityFilter = rar)}
			>
				{capitalize(rar)}
			</button>
		{/each}
	</div>

	{#if filtered.length === 0}
		<EmptyState icon="🏅" title="No achievements found" description="Try changing the filter or check back later." />
	{:else}
		<!-- Achievement Grid -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
			{#each filtered as ach (ach.id)}
				<div class="card card-hover {RARITY_GLOW[ach.rarity] || ''} shadow-lg animate-fade-in">
					<div class="flex items-start justify-between mb-3">
						<div>
							<h3 class="text-sm font-semibold text-white">{ach.name}</h3>
							{#if ach.description}
								<p class="text-xs text-zinc-500 mt-0.5 line-clamp-2">{ach.description}</p>
							{/if}
						</div>
						<RarityBadge rarity={ach.rarity} color={ach.rarity_color} />
					</div>

					<div class="flex items-center gap-4 text-xs text-zinc-400">
						{#if ach.xp_reward > 0}
							<span class="text-brand-400">✨ {fmt(ach.xp_reward)} XP</span>
						{/if}
						{#if ach.gold_reward > 0}
							<span class="text-gold-400">🪙 {fmt(ach.gold_reward)}</span>
						{/if}
					</div>

					<div class="mt-3 pt-3 border-t border-surface-300 flex items-center justify-between text-xs text-zinc-500">
						<span>{ach.earner_count} earned</span>
						<span>{ach.earn_pct}% of members</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Recent Earners -->
	{#if recent.length > 0}
		<div class="card">
			<h2 class="text-sm font-semibold text-zinc-300 mb-4">🎉 Recently Earned</h2>
			<div class="space-y-2">
				{#each recent as r}
					<div class="flex items-center gap-3 p-2 rounded-lg hover:bg-surface-200/50 transition-colors">
						<Avatar src={r.avatar_url} size={28} />
						<span class="text-sm text-zinc-300">{r.user_name}</span>
						<span class="text-xs text-zinc-500">earned</span>
						<span class="text-sm font-medium" style="color: {r.rarity_color}">{r.achievement_name}</span>
						<span class="ml-auto text-xs text-zinc-500">{timeAgo(r.earned_at)}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
{/if}
