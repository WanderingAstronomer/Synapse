<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Metrics, type RecentAchievement, type LeaderboardUser, type ActivityEvent } from '$lib/api';
	import HeroHeader from '$lib/components/HeroHeader.svelte';
	import MetricCard from '$lib/components/MetricCard.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import { fmt, timeAgo, eventTypeLabel } from '$lib/utils';

	let metrics = $state<Metrics | null>(null);
	let topUsers = $state<LeaderboardUser[]>([]);
	let recentAchievements = $state<RecentAchievement[]>([]);
	let recentEvents = $state<ActivityEvent[]>([]);
	let settings = $state<Record<string, unknown>>({});
	let loading = $state(true);

	onMount(async () => {
		try {
			const [m, lb, ach, s, act] = await Promise.all([
				api.getMetrics(),
				api.getLeaderboard('xp', 1, 5),
				api.getRecentAchievements(5),
				api.getPublicSettings(),
				api.getActivity(7, 10).catch(() => ({ events: [], daily: {} })),
			]);
			metrics = m;
			topUsers = lb.users;
			recentAchievements = ach.recent;
			settings = s;
			recentEvents = (act as { events: ActivityEvent[] }).events || [];
		} catch (e) {
			console.error('Failed to load overview:', e);
		} finally {
			loading = false;
		}
	});

	const title = $derived((settings.dashboard_title as string) || 'Synapse Community Dashboard');
	const subtitle = $derived((settings.dashboard_subtitle as string) || 'Community engagement at a glance');
	const emoji = $derived((settings.dashboard_hero_emoji as string) || '⚡');

	const RANK_MEDALS = ['🥇', '🥈', '🥉', '4', '5'];
	const champion = $derived(topUsers.length > 0 ? topUsers[0] : null);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<SynapseLoader size="lg" text="Loading dashboard..." />
	</div>
{:else}
	<HeroHeader
		{title}
		{subtitle}
		{emoji}
		metrics={metrics ? [
			{ label: 'Members', value: metrics.total_users, icon: '👥' },
			{ label: 'Total XP', value: metrics.total_xp, icon: '✨' },
			{ label: 'Active (7d)', value: metrics.active_users_7d, icon: '🔥' },
			{ label: 'Top Level', value: metrics.top_level, icon: '🏆' },
		] : []}
	/>

	<!-- Activity Ticker -->
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
									<span class="text-brand-400 font-medium">+{evt.xp_delta} XP</span>
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

	<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
		<!-- Top Members (2 cols) -->
		<div class="lg:col-span-2 card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold text-white">Top Members</h2>
				<a href="/leaderboard" class="text-xs text-brand-400 hover:text-brand-300 transition-colors">
					View all →
				</a>
			</div>

			{#if topUsers.length === 0}
				<EmptyState
					icon="🏆"
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
								<div class="absolute -top-2 left-1/2 -translate-x-1/2 text-xl animate-float">👑</div>
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
									<span class="text-brand-400 font-bold">{fmt(champion.xp)} XP</span>
									<span class="text-zinc-500">Level {champion.level}</span>
									{#if champion.gold > 0}
										<span class="text-gold-400">🪙 {fmt(champion.gold)}</span>
									{/if}
								</div>
								<div class="mt-2 max-w-xs">
									<ProgressBar value={champion.xp_progress} height={6} glow segments={8} />
								</div>
							</div>
							<span class="text-3xl font-extrabold text-amber-400/50">🥇</span>
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
								<p class="text-sm font-bold text-brand-400">{fmt(user.xp)} XP</p>
								{#if user.gold > 0}
									<p class="text-xs text-gold-400">🪙 {fmt(user.gold)}</p>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Right column: Recent Achievements -->
		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold text-white">Recent Achievements</h2>
				<a href="/achievements" class="text-xs text-brand-400 hover:text-brand-300 transition-colors">
					View all →
				</a>
			</div>

			{#if recentAchievements.length === 0}
				<EmptyState icon="🏅" title="No achievements earned yet" description="Badge hunters, your time will come." />
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
									<span class="text-sm font-medium" style="color: {ach.rarity_color}">{ach.achievement_name}</span>
									<RarityBadge rarity={ach.achievement_rarity} color={ach.rarity_color} />
								</div>
							</div>
							<span class="text-xs text-zinc-500 whitespace-nowrap">{timeAgo(ach.earned_at)}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}
