<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Metrics, type RecentAchievement, type LeaderboardUser, type ActivityEvent, type PageLayout, type CardConfig } from '$lib/api';
	import HeroHeader from '$lib/components/HeroHeader.svelte';
	import MetricCard from '$lib/components/MetricCard.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import EditableCard from '$lib/components/EditableCard.svelte';
	import CardPropertyPanel from '$lib/components/CardPropertyPanel.svelte';
	import { editMode, saveLayout } from '$lib/stores/editMode.svelte';
	import { siteSettings } from '$lib/stores/siteSettings.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import { fmt, timeAgo, eventTypeLabel } from '$lib/utils';
	import { RANK_MEDALS } from '$lib/constants';

	let metrics = $state<Metrics | null>(null);
	let topUsers = $state<LeaderboardUser[]>([]);
	let recentAchievements = $state<RecentAchievement[]>([]);
	let recentEvents = $state<ActivityEvent[]>([]);
	let layout = $state<PageLayout | null>(null);
	let loading = $state(true);
	let loadError = $state(false);

	let isEditing = $derived(editMode.canEdit);

	onMount(async () => {
		try {
			const [m, lb, ach, act, lay] = await Promise.all([
				api.getMetrics().catch(() => null),
				api.getLeaderboard('xp', 1, 5).catch(() => ({ total: 0, page: 1, page_size: 5, users: [] })),
				api.getRecentAchievements(5).catch(() => ({ recent: [] })),
				api.getActivity(7, 10).catch(() => ({ events: [], daily: {} })),
				api.getLayout('dashboard').catch(() => null),
			]);
			metrics = m;
			topUsers = (lb as any)?.users ?? [];
			recentAchievements = (ach as any)?.recent ?? [];
			recentEvents = (act as { events: ActivityEvent[] }).events || [];
			layout = lay;
		} catch (e) {
			console.error('Failed to load overview:', e);
			loadError = true;
		} finally {
			loading = false;
		}
	});

	let pageHeading = $derived(siteSettings.pageTitle('dashboard', 'Synapse Community Dashboard'));

	// ---- Layout-driven card rendering ----
	let sortedCards = $derived(
		layout?.cards
			?.filter((c) => isEditing || c.visible)
			.sort((a, b) => a.position - b.position) ?? []
	);

	// ---- Drag-and-drop reorder ----
	let dropTargetId = $state<string | null>(null);

	function handleReorder(draggedId: string, targetId: string) {
		if (!layout) return;
		dropTargetId = null;

		// Build new order: move dragged card to the position of the target
		const ids = sortedCards.map((c) => c.id);
		const fromIdx = ids.indexOf(draggedId);
		const toIdx = ids.indexOf(targetId);
		if (fromIdx === -1 || toIdx === -1 || fromIdx === toIdx) return;

		// Snapshot current positions for rollback
		const prevCards = layout.cards.map((c) => ({ ...c }));

		// Remove from old position, insert at new
		ids.splice(fromIdx, 1);
		ids.splice(toIdx, 0, draggedId);

		// Update local positions so UI reacts immediately
		layout.cards = layout.cards.map((c) => ({
			...c,
			position: ids.indexOf(c.id),
		}));

		// Save — on failure, revert to previous order and reload from server
		saveLayout('dashboard', { card_order: ids }).then((ok) => {
			if (!ok && layout) {
				layout.cards = prevCards;
				// Re-fetch to ensure consistency with server
				api.getLayout('dashboard').then((l) => { if (l) layout = l; }).catch(() => {});
			}
		});
	}

	// ---- Keyboard-accessible reorder helpers ----
	function handleMoveUp(cardId: string) {
		const idx = sortedCards.findIndex((c) => c.id === cardId);
		if (idx <= 0) return;
		handleReorder(cardId, sortedCards[idx - 1].id);
	}

	function handleMoveDown(cardId: string) {
		const idx = sortedCards.findIndex((c) => c.id === cardId);
		if (idx === -1 || idx >= sortedCards.length - 1) return;
		handleReorder(cardId, sortedCards[idx + 1].id);
	}

	// ---- Add Card ----
	const ADD_CARD_TYPES = [
		{ type: 'metric', label: 'Metric Card', icon: '📊' },
		{ type: 'hero_banner', label: 'Hero Banner', icon: '🖼️' },
		{ type: 'top_members', label: 'Top Members', icon: '🏆' },
		{ type: 'recent_achievements', label: 'Recent Achievements', icon: '🎖️' },
	];
	let addMenuOpen = $state(false);
	let addingCard = $state(false);

	async function addCard(cardType: string) {
		if (!layout || addingCard) return;
		addingCard = true;
		addMenuOpen = false;
		try {
			const newCard = await api.admin.createCard({
				page_layout_id: layout.id,
				card_type: cardType,
				position: sortedCards.length,
				grid_span: cardType === 'hero_banner' ? 3 : 1,
				title: cardType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
			});
			// Insert into local state so UI updates immediately
			layout.cards = [...layout.cards, newCard];
		} catch (err: any) {
			console.error('Failed to add card:', err);
		} finally {
			addingCard = false;
		}
	}

	function handleDeleteCard(cardId: string) {
		if (!layout) return;
		layout.cards = layout.cards.filter((c) => c.id !== cardId);
	}

	// Metric resolver — maps metric_key to live value
	const METRIC_META: Record<string, { icon: string; color: 'brand' | 'gold' | 'green' | 'blue' | 'pink' }> = {
		total_members: { icon: '', color: 'brand' },
		total_xp: { icon: '', color: 'brand' },
		total_gold: { icon: '', color: 'gold' },
		active_users_7d: { icon: '', color: 'green' },
		top_level: { icon: '', color: 'blue' },
		total_achievements: { icon: '', color: 'pink' },
	};

	function metricValue(key: string): number {
		if (!metrics) return 0;
		const map: Record<string, number> = {
			total_members: metrics.total_users,
			total_xp: metrics.total_xp,
			total_gold: metrics.total_gold,
			active_users_7d: metrics.active_users_7d,
			top_level: metrics.top_level,
			total_achievements: metrics.total_achievements_earned,
		};
		return map[key] ?? 0;
	}

	const champion = $derived(topUsers.length > 0 ? topUsers[0] : null);
</script>

<svelte:head>
	<title>{pageHeading}</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<SynapseLoader size="lg" text="Loading dashboard..." />
	</div>
{:else if loadError}
	<EmptyState
		title="Couldn't load dashboard"
		description="The API may be starting up. Try refreshing in a few seconds."
		variant="hero"
	/>
{:else if !layout}
	<EmptyState
		title="Dashboard not configured yet"
		description="Run the Setup wizard from Settings to create the dashboard layout and seed default cards."
		variant="hero"
	/>
{:else}
	<!-- Activity Ticker (always outside the card grid) -->
	{#if recentEvents.length > 0}
		<div class="relative overflow-hidden rounded-lg bg-surface-100 border border-surface-300 px-4 py-2 mb-6">
			<div class="flex items-center gap-2">
				<span class="flex-shrink-0 w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
				<span class="text-[10px] text-zinc-500 uppercase tracking-wider font-medium flex-shrink-0">Live</span>
				<div class="overflow-hidden flex-1">
					<div class="flex gap-8 animate-ticker whitespace-nowrap">
						{#each recentEvents as evt}
							<span class="text-xs text-zinc-400">
								<span class="text-zinc-200 font-medium">{evt.user_name}</span>
								{#if evt.event_type === 'ACHIEVEMENT_EARNED'}
									earned a badge
								{:else}
									{eventTypeLabel(evt.event_type).toLowerCase()}
								{/if}
								{#if evt.xp_delta > 0}
									<span class="text-brand-400 font-medium">+{evt.xp_delta} {currency.primary}</span>
								{/if}
								<span class="text-zinc-600 mx-1">·</span>
								<span class="text-zinc-600">{timeAgo(evt.timestamp)}</span>
							</span>
						{/each}
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- Card grid (layout-driven) -->
	{#if sortedCards.length > 0}
		<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 min-w-0">
			{#each sortedCards as card (card.id)}
				<!-- Hero Banner -->
				{#if card.card_type === 'hero_banner'}
					<EditableCard {card} showTitles={false} onreorder={handleReorder} onmoveup={handleMoveUp} onmovedown={handleMoveDown}>
						<HeroHeader
							title={card.title ?? undefined}
							subtitle={card.subtitle ?? undefined}
						/>
					</EditableCard>

				<!-- Metric card -->
				{:else if card.card_type === 'metric'}
					{@const key = (card.config_json?.metric_key as string) || 'total_members'}
					{@const meta = METRIC_META[key] || { icon: '', color: 'brand' as const }}
					<EditableCard {card} showTitles={false} onreorder={handleReorder} onmoveup={handleMoveUp} onmovedown={handleMoveDown}>
						<MetricCard
							label={card.title || key.replace(/_/g, ' ')}
							value={metricValue(key)}
							icon={meta.icon}
							color={meta.color}
						/>
					</EditableCard>

				<!-- Top Members -->
				{:else if card.card_type === 'top_members'}
					<EditableCard {card} onreorder={handleReorder} onmoveup={handleMoveUp} onmovedown={handleMoveDown}>
						<div class="card">
							<div class="flex items-center justify-between mb-4">
								<h2 class="text-lg font-semibold text-white">{card.title || 'Top Members'}</h2>
								<a href="/leaderboard" class="text-xs text-brand-400 hover:text-brand-300 transition-colors">
									View all →
								</a>
							</div>

							{#if topUsers.length === 0}
								<EmptyState
									title="No members yet"
									description="Invite Synapse to your server to start seeing activity!"
									variant="hero"
								/>
							{:else}
								<!-- Champion spotlight -->
								{#if champion}
									<div class="champion-card rounded-xl p-4 mb-4 border border-amber-500/20">
										<div class="relative z-10 flex items-center gap-4">
											<div class="relative flex-shrink-0">
												<div class="ring-3 ring-amber-500/30 rounded-full">
													<Avatar src={champion.avatar_url} size={56} ring={false} />
												</div>
											</div>
											<div class="flex-1 min-w-0">
												<div class="flex items-center gap-2">
													<p class="text-sm font-bold text-white">{champion.discord_name}</p>
													<span class="badge bg-amber-500/15 text-amber-400 border border-amber-500/30 text-[10px]">Champion</span>
												</div>
												<div class="flex items-center gap-3 mt-1 text-xs">
													<span class="text-brand-400 font-bold">{fmt(champion.xp)} {currency.primary}</span>
													<span class="text-zinc-500">Level {champion.level}</span>
													{#if champion.gold > 0}
														<span class="text-gold-400">{fmt(champion.gold)} Gold</span>
													{/if}
												</div>
												<div class="mt-2 max-w-xs">
													<ProgressBar value={champion.xp_progress} height={6} glow segments={8} />
												</div>
											</div>
											<span class="text-3xl font-extrabold text-amber-400/50">#1</span>
										</div>
									</div>
								{/if}

								<!-- Rest of top members -->
								<div class="space-y-2">
									{#each topUsers.slice(1) as user, i}
										<div class="flex items-center gap-3 p-3 rounded-lg bg-surface-200/50 hover:bg-surface-200 transition-all hover:scale-[1.01] group">
											<span class="w-6 text-center text-sm font-bold text-lg">
												{RANK_MEDALS[i + 1]}
											</span>
											<div class="group-hover:scale-105 transition-transform">
												<Avatar src={user.avatar_url} size={36} />
											</div>
											<div class="flex-1 min-w-0">
												<p class="text-sm font-medium text-zinc-200 truncate group-hover:text-white transition-colors">{user.discord_name}</p>
												<div class="flex items-center gap-2 mt-0.5">
													<span class="text-xs text-zinc-500">Lvl {user.level}</span>
													<div class="flex-1 max-w-20">
														<ProgressBar value={user.xp_progress} height={4} />
													</div>
												</div>
											</div>
											<div class="text-right">
												<p class="text-sm font-bold text-brand-400">{fmt(user.xp)} {currency.primary}</p>
												{#if user.gold > 0}
													<p class="text-xs text-gold-400">{fmt(user.gold)} Gold</p>
												{/if}
											</div>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					</EditableCard>

				<!-- Recent Achievements -->
				{:else if card.card_type === 'recent_achievements'}
					<EditableCard {card} onreorder={handleReorder} onmoveup={handleMoveUp} onmovedown={handleMoveDown}>
						<div class="card">
							<div class="flex items-center justify-between mb-4">
								<h2 class="text-lg font-semibold text-white">{card.title || 'Recent Achievements'}</h2>
								<a href="/achievements" class="text-xs text-brand-400 hover:text-brand-300 transition-colors">
									View all →
								</a>
							</div>

							{#if recentAchievements.length === 0}
								<EmptyState title="No achievements earned yet" description="Badge hunters, your time will come." />
							{:else}
								<div class="space-y-3">
									{#each recentAchievements as ach}
										<div class="flex items-center gap-3 p-3 rounded-lg bg-surface-200/50 hover:bg-surface-200 transition-all group hover:scale-[1.01]">
											<div class="group-hover:scale-105 transition-transform">
												<Avatar src={ach.avatar_url} size={36} />
											</div>
											<div class="flex-1 min-w-0">
												<p class="text-sm font-medium text-zinc-200 truncate">
													{ach.user_name}
													<span class="text-zinc-500 font-normal"> earned</span>
												</p>
												<div class="flex items-center gap-2 mt-0.5">
												<span class="text-sm font-medium" style="color: {ach.rarity_color ?? '#ffffff'}">{ach.achievement_name}</span>
											<RarityBadge rarity={String(ach.achievement_rarity ?? 'common')} color={String(ach.rarity_color ?? '#ffffff')} />
												</div>
											</div>
											<span class="text-xs text-zinc-500 whitespace-nowrap">{timeAgo(ach.earned_at)}</span>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					</EditableCard>
				{/if}
			{/each}

			<!-- Add Card button (edit mode only) -->
			{#if isEditing}
				<div class="relative">
					<button
						class="w-full h-full min-h-[8rem] rounded-xl border-2 border-dashed border-zinc-700 hover:border-brand-500/50 bg-surface-100/50 hover:bg-surface-200/50 transition-all flex flex-col items-center justify-center gap-2 text-zinc-500 hover:text-brand-400 cursor-pointer"
						onclick={() => { addMenuOpen = !addMenuOpen; }}
						disabled={addingCard}
					>
						<span class="text-2xl">{addingCard ? '...' : '+'}</span>
						<span class="text-sm font-medium">Add Card</span>
					</button>

					{#if addMenuOpen}
						<div class="absolute top-full left-0 mt-2 w-56 bg-surface-100 border border-surface-300 rounded-lg shadow-xl z-20 overflow-hidden">
							{#each ADD_CARD_TYPES as opt}
								<button
									class="w-full px-4 py-3 text-left text-sm text-zinc-300 hover:bg-surface-200 hover:text-white transition-colors flex items-center gap-3"
									onclick={() => addCard(opt.type)}
								>
									<span>{opt.icon}</span>
									<span>{opt.label}</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Card property panel (edit mode) -->
		<CardPropertyPanel cards={sortedCards} ondelete={handleDeleteCard} />
	{:else}
		<!-- Layout exists but has no visible cards -->
		<EmptyState
			title="No cards to display"
			description={isEditing ? 'Click the + button below to add your first card.' : 'The dashboard layout has no visible cards.'}
		/>

		{#if isEditing}
			<div class="mt-6 flex justify-center">
				<div class="relative">
					<button
						class="min-h-[8rem] w-64 rounded-xl border-2 border-dashed border-zinc-700 hover:border-brand-500/50 bg-surface-100/50 hover:bg-surface-200/50 transition-all flex flex-col items-center justify-center gap-2 text-zinc-500 hover:text-brand-400 cursor-pointer"
						onclick={() => { addMenuOpen = !addMenuOpen; }}
						disabled={addingCard}
					>
						<span class="text-2xl">{addingCard ? '...' : '+'}</span>
						<span class="text-sm font-medium">Add Card</span>
					</button>

					{#if addMenuOpen}
						<div class="absolute top-full left-0 mt-2 w-56 bg-surface-100 border border-surface-300 rounded-lg shadow-xl z-20 overflow-hidden">
							{#each ADD_CARD_TYPES as opt}
								<button
									class="w-full px-4 py-3 text-left text-sm text-zinc-300 hover:bg-surface-200 hover:text-white transition-colors flex items-center gap-3"
									onclick={() => addCard(opt.type)}
								>
									<span>{opt.icon}</span>
									<span>{opt.label}</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		{/if}
	{/if}
{/if}
