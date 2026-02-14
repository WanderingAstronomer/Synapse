<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type AdminUser, type Achievement } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import { fmt } from '$lib/utils';

	// Tabs
	let tab = $state<'currency' | 'achievement'>('currency');

	// User search
	let searchQuery = $state('');
	let searchResults = $state<AdminUser[]>([]);
	let selectedUser = $state<AdminUser | null>(null);
	let searchTimeout: ReturnType<typeof setTimeout>;

	// Currency form
	let xpAmount = $state(0);
	let goldAmount = $state(0);
	let reason = $state('');

	// Achievement form
	let achievements = $state<Achievement[]>([]);
	let selectedAchievementId = $state<number | null>(null);

	onMount(async () => {
		try {
			const res = await api.getAchievements();
			achievements = res.achievements;
		} catch (e) { console.error(e); }
	});

	function handleSearch() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(async () => {
			if (searchQuery.length < 1) { searchResults = []; return; }
			try {
				const res = await api.admin.searchUsers(searchQuery, 10);
				searchResults = res.users;
			} catch (e) { console.error(e); }
		}, 300);
	}

	function selectUser(u: AdminUser) {
		selectedUser = u;
		searchQuery = u.discord_name;
		searchResults = [];
	}

	async function awardXpGold() {
		if (!selectedUser) { flash.warning('Select a user first'); return; }
		if (xpAmount === 0 && goldAmount === 0) { flash.warning(`Enter ${currency.primary} or ${currency.secondary} amount`); return; }
		try {
			const res = await api.admin.awardXpGold({
				user_id: selectedUser.id,
				display_name: selectedUser.discord_name,
				xp: xpAmount,
				gold: goldAmount,
				reason: reason.trim(),
			});
			flash.success(`Awarded ${xpAmount} ${currency.primary} + ${goldAmount} ${currency.secondary} → now ${fmt(res.xp)} ${currency.primary}, Lvl ${res.level}`);
			xpAmount = 0;
			goldAmount = 0;
			reason = '';
		} catch (e: any) { flash.error(e.message); }
	}

	async function grantAchievement() {
		if (!selectedUser) { flash.warning('Select a user first'); return; }
		if (!selectedAchievementId) { flash.warning('Select an achievement'); return; }
		try {
			const res = await api.admin.grantAchievement({
				user_id: selectedUser.id,
				display_name: selectedUser.discord_name,
				achievement_id: selectedAchievementId,
			});
			flash.success(res.message);
			selectedAchievementId = null;
		} catch (e: any) { flash.error(e.message); }
	}
</script>

<svelte:head><title>Admin: Awards — Synapse</title></svelte:head>

<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">Manual Awards</h1>
	<p class="text-sm text-zinc-500 mt-1">Grant {currency.primary}, {currency.secondary}, or achievements to specific members.</p>
</div>

<!-- Tabs -->
<div class="flex gap-2 mb-6">
	<button
		class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:scale-[1.03] active:scale-[0.97]
			{tab === 'currency' ? 'bg-brand-600 text-white shadow-md shadow-brand-600/30' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => (tab = 'currency')}
	>
		{ currency.primary} & {currency.secondary}
	</button>
	<button
		class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:scale-[1.03] active:scale-[0.97]
			{tab === 'achievement' ? 'bg-brand-600 text-white shadow-md shadow-brand-600/30' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => (tab = 'achievement')}
	>
		Achievement
	</button>
</div>

<!-- User Search -->
<div class="card mb-6">
	<label class="label" for="user-search">Search Member</label>
	<div class="relative">
		<input
			id="user-search"
			class="input"
			placeholder="Start typing a username..."
			bind:value={searchQuery}
			oninput={handleSearch}
		/>
		{#if searchResults.length > 0}
			<div class="absolute z-10 top-full left-0 right-0 mt-1 bg-surface-100 border border-surface-300 rounded-lg shadow-xl overflow-hidden">
				{#each searchResults as u}
					<button
					class="w-full flex items-center gap-3 px-3 py-2 hover:bg-surface-200 transition-all duration-150 text-left hover:pl-4"
						onclick={() => selectUser(u)}
					>
						<span class="text-sm text-zinc-200">{u.discord_name}</span>
						<span class="text-xs text-zinc-500 ml-auto">Lvl {u.level} • {fmt(u.xp)} XP</span>
					</button>
				{/each}
			</div>
		{/if}
	</div>

	{#if selectedUser}
		<div class="mt-3 flex items-center gap-3 p-3 rounded-lg bg-surface-200">
			<span class="text-sm font-medium text-zinc-200">{selectedUser.discord_name}</span>
			<span class="text-xs text-zinc-500">Level {selectedUser.level} • {fmt(selectedUser.xp)} XP</span>
			<button class="ml-auto text-xs text-zinc-500 hover:text-zinc-300" onclick={() => { selectedUser = null; searchQuery = ''; }}>
				✕ Clear
			</button>
		</div>
	{/if}
</div>

{#if tab === 'currency'}
	<div class="card animate-fade-in">
		<h3 class="text-sm font-semibold text-zinc-300 mb-4">Award {currency.primary} & {currency.secondary}</h3>
		<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
			<div>
				<label class="label" for="award-xp">{currency.primary} Amount</label>
				<input id="award-xp" class="input" type="number" bind:value={xpAmount} placeholder="0" />
			</div>
			<div>
				<label class="label" for="award-gold">{currency.secondary} Amount</label>
				<input id="award-gold" class="input" type="number" bind:value={goldAmount} placeholder="0" />
			</div>
			<div>
				<label class="label" for="award-reason">Reason</label>
				<input id="award-reason" class="input" bind:value={reason} placeholder="Hackathon winner" />
			</div>
		</div>
		<button class="btn-primary mt-4" onclick={awardXpGold}>
			Award
		</button>
	</div>
{:else}
	<div class="card animate-fade-in">
		<h3 class="text-sm font-semibold text-zinc-300 mb-4">Grant Achievement</h3>
		<div>
			<label class="label" for="grant-ach">Achievement</label>
			<select id="grant-ach" class="input" bind:value={selectedAchievementId}>
				<option value={null}>— Select achievement —</option>
				{#each achievements as a}
					<option value={a.id}>{a.name} ({a.rarity})</option>
				{/each}
			</select>
		</div>
		<button class="btn-primary mt-4" onclick={grantAchievement}>
			Grant
		</button>
	</div>
{/if}
