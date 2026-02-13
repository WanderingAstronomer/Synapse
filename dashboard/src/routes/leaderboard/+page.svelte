<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type LeaderboardUser } from '$lib/api';
	import Avatar from '$lib/components/Avatar.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import { primaryCurrency, secondaryCurrency } from '$lib/stores/currency';
	import { fmt } from '$lib/utils';

	type Currency = 'xp' | 'gold' | 'level';

	let currency = $state<Currency>('xp');
	let page = $state(1);
	let pageSize = $state(20);
	let total = $state(0);
	let users = $state<LeaderboardUser[]>([]);
	let loading = $state(true);

	const RANK_MEDALS = ['🥇', '🥈', '🥉'];

	const tabs = $derived([
		{ value: 'xp' as Currency, label: $primaryCurrency, icon: '✨' },
		{ value: 'gold' as Currency, label: $secondaryCurrency, icon: '🪙' },
		{ value: 'level' as Currency, label: 'Level', icon: '📊' },
	]);

	async function load() {
		loading = true;
		try {
			const res = await api.getLeaderboard(currency, page, pageSize);
			users = res.users;
			total = res.total;
		} catch (e) {
			console.error('Leaderboard load failed:', e);
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function switchCurrency(c: Currency) {
		currency = c;
		page = 1;
		load();
	}

	function nextPage() {
		if (page * pageSize < total) {
			page++;
			load();
		}
	}

	function prevPage() {
		if (page > 1) {
			page--;
			load();
		}
	}

	const totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

	function valueFor(user: LeaderboardUser): string {
		if (currency === 'gold') return `🪙 ${fmt(user.gold)}`;
		if (currency === 'level') return `Lvl ${user.level}`;
		return `${fmt(user.xp)} ${$primaryCurrency}`;
	}

	const champion = $derived(users.length > 0 && page === 1 ? users[0] : null);
	const restUsers = $derived(page === 1 ? users.slice(1) : users);
</script>

<svelte:head><title>Leaderboard — Synapse</title></svelte:head>

<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">Leaderboard</h1>
	<p class="text-sm text-zinc-500 mt-1">See who's leading the charge.</p>
</div>

<!-- Tabs -->
<div class="flex gap-2 mb-6">
	{#each tabs as tab}
		<button
			class="px-4 py-2 rounded-lg text-sm font-medium transition-all
				{currency === tab.value
					? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20'
					: 'bg-surface-200 text-zinc-400 hover:text-zinc-200 hover:bg-surface-300'}"
			onclick={() => switchCurrency(tab.value)}
		>
			{tab.icon} {tab.label}
		</button>
	{/each}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading leaderboard..." />
	</div>
{:else if users.length === 0}
	<EmptyState
		icon="🏆"
		title="Leaderboard is empty"
		description="No members have earned {$primaryCurrency} yet. Invite Synapse to your server to start tracking engagement!"
		variant="hero"
	/>
{:else}
	<!-- Champion Spotlight (page 1 only) -->
	{#if champion}
		<div class="champion-card card mb-6 animate-slide-up">
			<div class="relative z-10 flex items-center gap-6 p-2">
				<!-- Crown + avatar -->
				<div class="relative flex-shrink-0">
					<div class="absolute -top-3 left-1/2 -translate-x-1/2 text-2xl animate-float z-10">👑</div>
					<div class="ring-4 ring-amber-500/30 rounded-full">
						<Avatar src={champion.avatar_url} size={72} ring={false} />
					</div>
				</div>

				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-2 mb-1">
						<span class="text-lg font-bold text-white">{champion.discord_name}</span>
						<span class="badge bg-amber-500/15 text-amber-400 border border-amber-500/30">🥇 Champion</span>
					</div>
					<div class="flex items-center gap-4 text-sm mb-3">
						<span class="text-brand-400 font-bold">{fmt(champion.xp)} {$primaryCurrency}</span>
						<span class="text-zinc-500">Level {champion.level}</span>
						{#if champion.gold > 0}
							<span class="text-gold-400">🪙 {fmt(champion.gold)}</span>
						{/if}
					</div>
					<div class="max-w-xs">
						<div class="flex justify-between items-center mb-1">
							<span class="text-[10px] text-zinc-500 uppercase tracking-wider">Progress to Level {champion.level + 1}</span>
							<span class="text-xs text-zinc-400 font-mono">{(champion.xp_progress * 100).toFixed(0)}%</span>
						</div>
						<ProgressBar value={champion.xp_progress} height={10} glow segments={10} />
					</div>
				</div>

				<div class="text-right flex-shrink-0">
					<p class="text-4xl font-extrabold text-glow-gold text-amber-400">#1</p>
				</div>
			</div>
		</div>
	{/if}

	<!-- Rest of leaderboard -->
	<div class="card p-0 overflow-hidden">
		<table class="w-full">
			<thead>
				<tr class="border-b border-surface-300 text-xs text-zinc-500 uppercase tracking-wider">
					<th class="px-4 py-3 text-left w-12">#</th>
					<th class="px-4 py-3 text-left">Member</th>
					<th class="px-4 py-3 text-left w-48">Progress to Next Level</th>
					<th class="px-4 py-3 text-right">{currency === 'gold' ? $secondaryCurrency : currency === 'level' ? 'Level' : $primaryCurrency}</th>
				</tr>
			</thead>
			<tbody>
				{#each restUsers as user, i}
					<tr class="border-b border-surface-300/50 hover:bg-surface-200/50 transition-all group">
						<td class="px-4 py-3">
							<span class="text-sm font-bold {user.rank <= 3 ? 'text-lg' : 'text-zinc-500'}">
								{user.rank <= 3 ? RANK_MEDALS[user.rank - 1] : user.rank}
							</span>
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-3">
								<div class="group-hover:scale-105 transition-transform">
									<Avatar src={user.avatar_url} size={32} />
								</div>
								<div>
									<p class="text-sm font-medium text-zinc-200 group-hover:text-white transition-colors">{user.discord_name}</p>
									<p class="text-xs text-zinc-500">Level {user.level}</p>
								</div>
							</div>
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-2">
								<div class="flex-1">
									<ProgressBar value={user.xp_progress} height={8} segments={5} />
								</div>
								<span class="text-[10px] text-zinc-500 font-mono w-8 text-right">{(user.xp_progress * 100).toFixed(0)}%</span>
							</div>
						</td>
						<td class="px-4 py-3 text-right">
							<span class="text-sm font-bold text-brand-400">{valueFor(user)}</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Pagination -->
	<div class="flex items-center justify-between mt-4">
		<p class="text-xs text-zinc-500">
			Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {fmt(total)}
		</p>
		<div class="flex gap-2">
			<button class="btn-secondary text-xs" onclick={prevPage} disabled={page <= 1}>
				← Prev
			</button>
			<span class="px-3 py-2 text-xs text-zinc-500">
				{page} / {totalPages}
			</span>
			<button class="btn-secondary text-xs" onclick={nextPage} disabled={page >= totalPages}>
				Next →
			</button>
		</div>
	</div>
{/if}
