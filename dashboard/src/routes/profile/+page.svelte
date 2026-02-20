<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type MemberProfile,
		type MemberAchievement,
		type MemberActivityEvent,
		type InventoryItem,
		type ShopItem,
	} from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import { fmt, timeAgo, eventTypeLabel, eventColor } from '$lib/utils';
	import AuthPrompt from '$lib/components/AuthPrompt.svelte';

	// ---------------------------------------------------------------------------
	//  State
	// ---------------------------------------------------------------------------
	let profile = $state<MemberProfile | null>(null);
	let achievements = $state<MemberAchievement[]>([]);
	let activity = $state<MemberActivityEvent[]>([]);
	let inventory = $state<InventoryItem[]>([]);
	let shopItems = $state<ShopItem[]>([]);
	let loading = $state(true);
	let loadError = $state(false);

	/** Track which activity event's "Why" trace is expanded */
	let expandedTraceId = $state<number | null>(null);

	/** Track equip/unequip in-flight to disable buttons */
	let equipLoading = $state<number | null>(null);

	// ---------------------------------------------------------------------------
	//  Active tab
	// ---------------------------------------------------------------------------
	type Tab = 'stats' | 'achievements' | 'activity' | 'inventory';
	let activeTab = $state<Tab>('stats');

	const tabs: { value: Tab; label: string }[] = [
		{ value: 'stats', label: 'Stats' },
		{ value: 'achievements', label: 'Achievements' },
		{ value: 'activity', label: 'Activity' },
		{ value: 'inventory', label: 'Inventory' },
	];

	// ---------------------------------------------------------------------------
	//  Load data
	// ---------------------------------------------------------------------------
	onMount(async () => {
		if (!auth.user) {
			loading = false;
			return;
		}
		try {
			const [p, a, act, inv, shop] = await Promise.all([
				api.member.getProfile().catch(() => null),
				api.member.getAchievements().catch(() => ({ achievements: [] })),
				api.member.getActivity(30, 50).catch(() => ({ events: [] })),
				api.shop.getInventory().catch(() => ({ inventory: [] })),
				api.shop.getItems().catch(() => ({ items: [] })),
			]);
			profile = p;
			achievements = a?.achievements ?? [];
			activity = act?.events ?? [];
			inventory = inv?.inventory ?? [];
			shopItems = shop?.items ?? [];
		} catch {
			loadError = true;
		} finally {
			loading = false;
		}
	});

	// ---------------------------------------------------------------------------
	//  Helpers
	// ---------------------------------------------------------------------------
	function itemName(itemId: number): string {
		return shopItems.find((i) => i.id === itemId)?.name ?? `Item #${itemId}`;
	}

	async function toggleEquip(inv: InventoryItem) {
		equipLoading = inv.id;
		try {
			if (inv.is_equipped) {
				const updated = await api.shop.unequip(inv.item_id);
				inventory = inventory.map((i) => (i.id === inv.id ? updated : i));
			} else {
				const updated = await api.shop.equip(inv.item_id);
				inventory = inventory.map((i) => (i.id === inv.id ? updated : i));
			}
		} catch (e) {
			console.error('Equip toggle failed:', e);
		} finally {
			equipLoading = null;
		}
	}
</script>

<svelte:head><title>My Profile — Synapse</title></svelte:head>

{#if auth.loading}
	<div class="flex items-center justify-center h-64">
		<SynapseLoader text="Loading..." />
	</div>
{:else if !auth.user}
	<div class="flex items-center justify-center h-64">
		<AuthPrompt message="Sign in to view your profile" />
	</div>
{:else if loading}
	<div class="flex items-center justify-center h-64">
		<SynapseLoader text="Loading your profile..." />
	</div>
{:else if loadError || !profile?.user}
	<div class="flex items-center justify-center h-64">
		<EmptyState
			title="Profile unavailable"
			description="We couldn't load your profile. Please try again later."
			variant="hero"
		/>
	</div>
{:else}
	<!-- Profile Header -->
	<div class="card mb-6">
		<div class="flex items-center gap-6 p-2">
			<div class="flex-shrink-0">
				<Avatar src={profile.user.avatar_url} size={80} ring={true} />
			</div>
			<div class="flex-1 min-w-0">
				<h1 class="text-2xl font-bold text-white">{profile.user.discord_name}</h1>
				<p class="text-sm text-zinc-500 mt-1">Level {profile.user.level}</p>
				<div class="max-w-sm mt-3">
					<div class="flex justify-between items-center mb-1">
						<span class="text-[10px] text-zinc-500 uppercase tracking-wider">
							Progress to Level {profile.user.level + 1}
						</span>
						<span class="text-xs text-zinc-400 font-mono">
							{(profile.user.xp_progress * 100).toFixed(0)}%
						</span>
					</div>
					<ProgressBar value={profile.user.xp_progress} height={14} glow segments={10} />
				</div>
			</div>
			{#if profile.user.created_at}
				<div class="text-right flex-shrink-0 hidden sm:block">
					<p class="text-xs text-zinc-500">Joined</p>
					<p class="text-sm text-zinc-400">{timeAgo(profile.user.created_at)}</p>
				</div>
			{/if}
		</div>
	</div>

	<!-- Stat Cards Row -->
	<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">{currency.primary}</p>
			<p class="text-2xl font-bold text-brand-400">{fmt(profile.user.xp)}</p>
			{#if profile.ranks.xp}
				<p class="text-xs text-zinc-500 mt-1">Rank #{fmt(profile.ranks.xp)}</p>
			{/if}
		</div>
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">{currency.secondary}</p>
			<p class="text-2xl font-bold text-gold-400">{fmt(profile.user.gold)}</p>
			{#if profile.ranks.gold}
				<p class="text-xs text-zinc-500 mt-1">Rank #{fmt(profile.ranks.gold)}</p>
			{/if}
		</div>
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">Achievements</p>
			<p class="text-2xl font-bold text-purple-400">{fmt(achievements.length)}</p>
		</div>
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">Inventory</p>
			<p class="text-2xl font-bold text-emerald-400">{fmt(inventory.length)}</p>
		</div>
	</div>

	<!-- Tab Navigation -->
	<div class="flex gap-2 mb-6" role="tablist" aria-label="Profile sections">
		{#each tabs as tab}
			<button
				role="tab"
				aria-selected={activeTab === tab.value}
				class="px-4 py-2 rounded-lg text-sm font-medium transition-all
					{activeTab === tab.value
						? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20'
						: 'bg-surface-200 text-zinc-400 hover:text-zinc-200 hover:bg-surface-300'}"
				onclick={() => (activeTab = tab.value)}
			>
				{tab.label}
			</button>
		{/each}
	</div>

	<!-- Tab Panels -->
	{#if activeTab === 'stats'}
		<!-- Stats detail panel -->
		<div class="card">
			<h2 class="text-lg font-semibold text-white mb-4">Detailed Stats</h2>
			<div class="grid gap-3">
				<div class="flex justify-between items-center py-2 border-b border-surface-300/50">
					<span class="text-sm text-zinc-400">Total {currency.primary}</span>
					<span class="text-sm font-bold text-brand-400">{fmt(profile.user.xp)}</span>
				</div>
				<div class="flex justify-between items-center py-2 border-b border-surface-300/50">
					<span class="text-sm text-zinc-400">Total {currency.secondary}</span>
					<span class="text-sm font-bold text-gold-400">{fmt(profile.user.gold)}</span>
				</div>
				<div class="flex justify-between items-center py-2 border-b border-surface-300/50">
					<span class="text-sm text-zinc-400">Level</span>
					<span class="text-sm font-bold text-zinc-200">{profile.user.level}</span>
				</div>
				<div class="flex justify-between items-center py-2 border-b border-surface-300/50">
					<span class="text-sm text-zinc-400">{currency.primary} needed for next level</span>
					<span class="text-sm font-bold text-zinc-400">{fmt(profile.user.xp_for_next)}</span>
				</div>
				<div class="flex justify-between items-center py-2 border-b border-surface-300/50">
					<span class="text-sm text-zinc-400">{currency.primary} Rank</span>
					<span class="text-sm font-bold text-brand-400">
						{profile.ranks.xp ? `#${fmt(profile.ranks.xp)}` : '—'}
						<span class="text-xs text-zinc-500 ml-1">of {fmt(profile.ranks.total_users)}</span>
					</span>
				</div>
				<div class="flex justify-between items-center py-2">
					<span class="text-sm text-zinc-400">{currency.secondary} Rank</span>
					<span class="text-sm font-bold text-gold-400">
						{profile.ranks.gold ? `#${fmt(profile.ranks.gold)}` : '—'}
						<span class="text-xs text-zinc-500 ml-1">of {fmt(profile.ranks.total_users)}</span>
					</span>
				</div>
			</div>
		</div>

	{:else if activeTab === 'achievements'}
		{#if achievements.length === 0}
			<EmptyState
				title="No achievements yet"
				description="Keep engaging with the community to earn achievements!"
				variant="hero"
			/>
		{:else}
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
				{#each achievements as ach}
					<div class="card hover:bg-surface-200/50 transition-all">
						<div class="flex items-start gap-3">
							{#if ach.badge_image}
								<img src={ach.badge_image} alt={ach.name} class="w-10 h-10 rounded-lg object-cover flex-shrink-0" />
							{:else}
								<div class="w-10 h-10 rounded-lg bg-surface-300 flex items-center justify-center flex-shrink-0">
									<span class="text-lg">🏆</span>
								</div>
							{/if}
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-white truncate">{ach.name}</p>
								{#if ach.rarity}
									<RarityBadge rarity={ach.rarity} size="sm" />
								{/if}
								{#if ach.description}
									<p class="text-xs text-zinc-500 mt-1 line-clamp-2">{ach.description}</p>
								{/if}
								<div class="flex items-center gap-2 mt-2 text-xs">
									{#if ach.xp_reward > 0}
										<span class="text-brand-400">+{fmt(ach.xp_reward)} {currency.primary}</span>
									{/if}
									{#if ach.gold_reward > 0}
										<span class="text-gold-400">+{fmt(ach.gold_reward)} {currency.secondary}</span>
									{/if}
								</div>
								{#if ach.earned_at}
									<p class="text-[10px] text-zinc-600 mt-1">Earned {timeAgo(ach.earned_at)}</p>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}

	{:else if activeTab === 'activity'}
		{#if activity.length === 0}
			<EmptyState
				title="No recent activity"
				description="Your activity timeline will appear here once you start interacting."
				variant="hero"
			/>
		{:else}
			<div class="space-y-2">
				{#each activity as event}
					<div class="card hover:bg-surface-200/50 transition-all">
						<div class="flex items-center gap-4">
							<!-- Event type badge -->
							<div
								class="w-2 h-2 rounded-full flex-shrink-0"
								style="background-color: {eventColor(event.event_type)}"
							></div>
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-medium text-zinc-200">
										{eventTypeLabel(event.event_type)}
									</span>
									{#if event.xp_delta > 0}
										<span class="text-xs text-brand-400">+{fmt(event.xp_delta)} {currency.primary}</span>
									{/if}
									{#if event.star_delta > 0}
										<span class="text-xs text-gold-400">+{fmt(event.star_delta)} {currency.secondary}</span>
									{/if}
								</div>
								{#if event.timestamp}
									<p class="text-xs text-zinc-500">{timeAgo(event.timestamp)}</p>
								{/if}
							</div>

							<!-- "Why" trace toggle -->
							{#if event.why_trace}
								<button
									class="text-xs text-brand-400 hover:text-brand-300 transition-colors flex-shrink-0"
									onclick={() => (expandedTraceId = expandedTraceId === event.id ? null : event.id)}
									aria-expanded={expandedTraceId === event.id}
								>
									{expandedTraceId === event.id ? 'Hide' : 'Why?'}
								</button>
							{/if}
						</div>

						<!-- "Why" trace detail -->
						{#if event.why_trace && expandedTraceId === event.id}
							<div class="mt-3 pt-3 border-t border-surface-300/50">
								<p class="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Reward Trace</p>
								{#if event.why_trace.matched_rules.length > 0}
									<div class="mb-2">
										<p class="text-xs text-zinc-500 mb-1">Matched Rules:</p>
										<div class="flex flex-wrap gap-1">
											{#each event.why_trace.matched_rules as rule}
												<span class="px-2 py-0.5 rounded bg-surface-300 text-xs text-zinc-300">
													{typeof rule === 'object' && rule !== null && 'name' in rule ? (rule as { name: string }).name : JSON.stringify(rule)}
												</span>
											{/each}
										</div>
									</div>
								{/if}
								{#if Object.keys(event.why_trace.outcomes_applied).length > 0}
									<div class="mb-2">
										<p class="text-xs text-zinc-500 mb-1">Outcomes Applied:</p>
										<div class="flex flex-wrap gap-2">
											{#each Object.entries(event.why_trace.outcomes_applied) as [key, val]}
												<span class="text-xs text-zinc-300">
													<span class="text-zinc-500">{key}:</span> {val}
												</span>
											{/each}
										</div>
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}

	{:else if activeTab === 'inventory'}
		{#if inventory.length === 0}
			<EmptyState
				title="Inventory empty"
				description="Visit the marketplace to purchase cosmetic items!"
				variant="hero"
			/>
		{:else}
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
				{#each inventory as inv}
					{@const item = shopItems.find((i) => i.id === inv.item_id)}
					<div class="card hover:bg-surface-200/50 transition-all">
						<div class="flex items-start gap-3">
							<div class="w-10 h-10 rounded-lg bg-surface-300 flex items-center justify-center flex-shrink-0">
								<span class="text-lg">{inv.is_equipped ? '✨' : '📦'}</span>
							</div>
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-white truncate">{itemName(inv.item_id)}</p>
								{#if item?.description}
									<p class="text-xs text-zinc-500 mt-0.5 line-clamp-2">{item.description}</p>
								{/if}
								<div class="flex items-center gap-2 mt-2">
									{#if inv.is_equipped}
										<span class="text-xs text-emerald-400 font-medium">Equipped</span>
									{:else}
										<span class="text-xs text-zinc-500">Not equipped</span>
									{/if}
									{#if inv.purchased_at}
										<span class="text-xs text-zinc-600">· {timeAgo(inv.purchased_at)}</span>
									{/if}
								</div>
							</div>
							<button
								class="text-xs px-3 py-1.5 rounded-lg transition-all flex-shrink-0
									{inv.is_equipped
										? 'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20'
										: 'bg-brand-500/10 text-brand-400 hover:bg-brand-500/20 border border-brand-500/20'}"
								disabled={equipLoading === inv.id}
								onclick={() => toggleEquip(inv)}
							>
								{#if equipLoading === inv.id}
									...
								{:else}
									{inv.is_equipped ? 'Unequip' : 'Equip'}
								{/if}
							</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
{/if}
