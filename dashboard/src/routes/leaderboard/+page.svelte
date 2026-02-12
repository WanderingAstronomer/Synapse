<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type LeaderboardUser } from '$lib/api';
	import Avatar from '$lib/components/Avatar.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { fmt } from '$lib/utils';

	type Currency = 'xp' | 'gold' | 'level';

	let currency = $state<Currency>('xp');
	let page = $state(1);
	let pageSize = $state(20);
	let total = $state(0);
	let users = $state<LeaderboardUser[]>([]);
	let loading = $state(true);

	const RANK_MEDALS = ['🥇', '🥈', '🥉'];

	const tabs: { value: Currency; label: string; icon: string }[] = [
		{ value: 'xp', label: 'XP', icon: '✨' },
		{ value: 'gold', label: 'Gold', icon: '🪙' },
		{ value: 'level', label: 'Level', icon: '📊' },
	];

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
		return `${fmt(user.xp)} XP`;
	}
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
			class="px-4 py-2 rounded-lg text-sm font-medium transition-colors
				{currency === tab.value
					? 'bg-brand-600 text-white'
					: 'bg-surface-200 text-zinc-400 hover:text-zinc-200 hover:bg-surface-300'}"
			onclick={() => switchCurrency(tab.value)}
		>
			{tab.icon} {tab.label}
		</button>
	{/each}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if users.length === 0}
	<EmptyState icon="🏆" title="Leaderboard is empty" description="No members have earned XP yet." />
{:else}
	<div class="card p-0 overflow-hidden">
		<table class="w-full">
			<thead>
				<tr class="border-b border-surface-300 text-xs text-zinc-500 uppercase tracking-wider">
					<th class="px-4 py-3 text-left w-12">#</th>
					<th class="px-4 py-3 text-left">Member</th>
					<th class="px-4 py-3 text-right">Progress</th>
					<th class="px-4 py-3 text-right">{currency === 'gold' ? 'Gold' : currency === 'level' ? 'Level' : 'XP'}</th>
				</tr>
			</thead>
			<tbody>
				{#each users as user, i}
					<tr class="border-b border-surface-300/50 hover:bg-surface-200/50 transition-colors">
						<td class="px-4 py-3">
							<span class="text-sm font-bold {user.rank <= 3 ? 'text-lg' : 'text-zinc-500'}">
								{user.rank <= 3 ? RANK_MEDALS[user.rank - 1] : user.rank}
							</span>
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-3">
								<Avatar src={user.avatar_url} size={32} />
								<div>
									<p class="text-sm font-medium text-zinc-200">{user.discord_name}</p>
									<p class="text-xs text-zinc-500">Level {user.level}</p>
								</div>
							</div>
						</td>
						<td class="px-4 py-3 w-32">
							<ProgressBar value={user.xp_progress} height={6} />
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
