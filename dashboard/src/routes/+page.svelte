<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Metrics, type RecentAchievement, type LeaderboardUser } from '$lib/api';
	import HeroHeader from '$lib/components/HeroHeader.svelte';
	import MetricCard from '$lib/components/MetricCard.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { fmt, timeAgo } from '$lib/utils';

	let metrics = $state<Metrics | null>(null);
	let topUsers = $state<LeaderboardUser[]>([]);
	let recentAchievements = $state<RecentAchievement[]>([]);
	let settings = $state<Record<string, unknown>>({});
	let loading = $state(true);

	onMount(async () => {
		try {
			const [m, lb, ach, s] = await Promise.all([
				api.getMetrics(),
				api.getLeaderboard('xp', 1, 5),
				api.getRecentAchievements(5),
				api.getPublicSettings(),
			]);
			metrics = m;
			topUsers = lb.users;
			recentAchievements = ach.recent;
			settings = s;
		} catch (e) {
			console.error('Failed to load overview:', e);
		} finally {
			loading = false;
		}
	});

	const title = $derived((settings.dashboard_title as string) || 'Synapse Club Pulse');
	const subtitle = $derived((settings.dashboard_subtitle as string) || 'Community engagement at a glance');
	const emoji = $derived((settings.dashboard_hero_emoji as string) || '⚡');

	const RANK_MEDALS = ['🥇', '🥈', '🥉', '4', '5'];
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
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

	<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
		<!-- Top Members -->
		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold text-white">Top Members</h2>
				<a href="/leaderboard" class="text-xs text-brand-400 hover:text-brand-300 transition-colors">
					View all →
				</a>
			</div>

			{#if topUsers.length === 0}
				<EmptyState icon="🏆" title="No members yet" description="XP will start flowing once the bot is active." />
			{:else}
				<div class="space-y-3">
					{#each topUsers as user, i}
						<div class="flex items-center gap-3 p-3 rounded-lg bg-surface-200/50 hover:bg-surface-200 transition-colors">
							<span class="w-6 text-center text-sm font-bold {i < 3 ? 'text-lg' : 'text-zinc-500'}">
								{i < 3 ? RANK_MEDALS[i] : i + 1}
							</span>
							<Avatar src={user.avatar_url} size={36} />
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-zinc-200 truncate">{user.discord_name}</p>
								<div class="flex items-center gap-2 mt-0.5">
									<span class="text-xs text-zinc-500">Lvl {user.level}</span>
									<ProgressBar value={user.xp_progress} height={4} />
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

		<!-- Recent Achievements -->
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
						<div class="flex items-center gap-3 p-3 rounded-lg bg-surface-200/50 hover:bg-surface-200 transition-colors">
							<Avatar src={ach.avatar_url} size={36} />
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
