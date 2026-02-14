<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Achievement, type RecentAchievement, type PageLayout } from '$lib/api';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import EditableCard from '$lib/components/EditableCard.svelte';
	import CardPropertyPanel from '$lib/components/CardPropertyPanel.svelte';
	import { editMode } from '$lib/stores/editMode.svelte';
	import { siteSettings } from '$lib/stores/siteSettings.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import { fmt, timeAgo, capitalize } from '$lib/utils';

	let achievements = $state<Achievement[]>([]);
	let recent = $state<RecentAchievement[]>([]);
	let layout = $state<PageLayout | null>(null);
	let loading = $state(true);
	let categoryFilter = $state('');
	let rarityFilter = $state('');

	let isEditing = $derived(editMode.canEdit);

	let heading = $derived(siteSettings.pageTitle('achievements', 'Achievements'));

	onMount(async () => {
		try {
			const [achRes, recRes, lay] = await Promise.all([
				api.getAchievements(),
				api.getRecentAchievements(10),
				api.getLayout('achievements').catch(() => null),
			]);
			achievements = achRes.achievements;
			recent = recRes.recent;
			layout = lay;
		} catch (e) {
			console.error('Achievements load failed:', e);
		} finally {
			loading = false;
		}
	});

	const categories = $derived([...new Set(achievements.map((a) => a.category).filter((c): c is string => c !== null))].sort());
	const rarities = $derived([...new Set(achievements.map((a) => a.rarity).filter((r): r is string => r !== null))]);

	const filtered = $derived(
		achievements.filter((a) => {
			if (categoryFilter && a.category !== categoryFilter) return false;
			if (rarityFilter && a.rarity !== rarityFilter) return false;
			return true;
		})
	);

	const RARITY_BORDER: Record<string, string> = {
		legendary: 'rarity-legendary',
		epic: 'rarity-epic',
		rare: 'rarity-rare',
		uncommon: 'rarity-uncommon',
		common: 'rarity-common',
	};

	const RARITY_ICON_BG: Record<string, string> = {
		legendary: 'bg-amber-500/15 border-amber-500/30',
		epic: 'bg-purple-500/15 border-purple-500/30',
		rare: 'bg-blue-500/15 border-blue-500/30',
		uncommon: 'bg-emerald-500/15 border-emerald-500/30',
		common: 'bg-zinc-500/10 border-zinc-500/20',
	};

	const CATEGORY_ICONS: Record<string, string> = {
		social: '',
		coding: '',
		engagement: '',
		special: '',
	};

	let sortedCards = $derived(
		layout?.cards
			?.filter((c) => isEditing || c.visible)
			.sort((a, b) => a.position - b.position) ?? []
	);
	let wrapCard = $derived(sortedCards.find((c) => c.card_type === 'achievement_grid'));
</script>

<svelte:head><title>{heading} — Synapse</title></svelte:head>

{#snippet pageContent()}
<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">{heading}</h1>
	<p class="text-sm text-zinc-500 mt-1">Collect badges, earn rewards, show off your dedication.</p>
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading achievements..." />
	</div>
{:else}
	<!-- Filters -->
	<div class="flex flex-wrap gap-2 mb-6">
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
				{!categoryFilter ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => (categoryFilter = '')}
		>
			All Categories
		</button>
		{#each categories as cat}
			<button
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
					{categoryFilter === cat ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
				onclick={() => (categoryFilter = cat)}
			>
				{CATEGORY_ICONS[cat] ?? ''} {capitalize(cat)}
			</button>
		{/each}
		<div class="w-px bg-surface-400 mx-1"></div>
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
				{!rarityFilter ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => (rarityFilter = '')}
		>
			All Rarities
		</button>
		{#each rarities as rar}
			<button
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
					{rarityFilter === rar ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
				onclick={() => (rarityFilter = rar)}
			>
				{capitalize(rar)}
			</button>
		{/each}
	</div>

	{#if filtered.length === 0}
		<EmptyState title="No achievements found" description="Try changing the filter or check back later." />
	{:else}
		<!-- Achievement Grid -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
			{#each filtered as ach (ach.id)}
			<div class="card card-hover {RARITY_BORDER[ach.rarity ?? 'common'] ?? ''} group hover:scale-[1.02] transition-all duration-200 animate-fade-in">
				<div class="flex items-start gap-3 mb-3">
					<!-- Badge icon -->
					<div class="w-12 h-12 rounded-xl border flex items-center justify-center flex-shrink-0 {RARITY_ICON_BG[ach.rarity ?? 'common'] ?? RARITY_ICON_BG.common}">
						{#if ach.badge_image}
							<img src={ach.badge_image} alt={ach.name} class="w-8 h-8 object-contain" />
						{:else}
							<span class="text-2xl">{CATEGORY_ICONS[ach.category ?? ''] ?? ''}</span>
						{/if}
					</div>
					<div class="flex-1 min-w-0">
						<h3 class="text-sm font-semibold text-white group-hover:text-brand-300 transition-colors">{ach.name}</h3>
						{#if ach.description}
							<p class="text-xs text-zinc-500 mt-0.5 line-clamp-2">{ach.description}</p>
						{/if}
					</div>
					<RarityBadge rarity={ach.rarity ?? 'common'} />
					</div>

					<!-- Rewards -->
					<div class="flex items-center gap-3 text-xs mb-3">
						{#if ach.xp_reward > 0}
							<span class="text-brand-400 font-medium">{fmt(ach.xp_reward)} {currency.primary}</span>
						{/if}
						{#if ach.gold_reward > 0}
							<span class="text-gold-400 font-medium">{fmt(ach.gold_reward)} Gold</span>
						{/if}
					</div>

					<!-- Earn rate bar -->
					<div class="pt-3 border-t border-surface-300/50">
						<div class="flex items-center justify-between text-xs text-zinc-500 mb-1.5">
							<span>{ach.earner_count} earned</span>
							<span>{ach.earn_pct}%</span>
						</div>
						<ProgressBar value={ach.earn_pct / 100} height={4} />
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Recent Earners -->
	{#if recent.length > 0}
		<div class="card">
			<h2 class="text-sm font-semibold text-zinc-300 mb-4">Recently Earned</h2>
			<div class="space-y-2">
				{#each recent as r}
					<div class="flex items-center gap-3 p-2.5 rounded-lg hover:bg-surface-200/50 transition-all hover:scale-[1.01]">
						<Avatar src={r.avatar_url} size={28} />
						<span class="text-sm text-zinc-300">{r.user_name}</span>
						<span class="text-xs text-zinc-500">earned</span>
					<span class="text-sm font-medium" style="color: {r.rarity_color ?? '#ffffff'}">{r.achievement_name}</span>
					<RarityBadge rarity={r.achievement_rarity ?? 'common'} />
						<span class="ml-auto text-xs text-zinc-500">{timeAgo(r.earned_at)}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
{/if}
{/snippet}

{#if wrapCard}
<EditableCard card={wrapCard} showTitles={false}>
	{@render pageContent()}
</EditableCard>
<CardPropertyPanel cards={sortedCards} />
{:else}
{@render pageContent()}
{/if}
