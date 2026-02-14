<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type TypeDefault,
		type TypeDefaultUpsert,
		type ChannelOverrideRow,
		type ChannelOverrideUpsert,
		type DiscordChannel,
	} from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import { INTERACTION_TYPES } from '$lib/constants';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------
	let activeTab = $state<'defaults' | 'overrides'>('defaults');
	let loading = $state(true);

	// Data
	let defaults = $state<TypeDefault[]>([]);
	let overrides = $state<ChannelOverrideRow[]>([]);
	let channels = $state<DiscordChannel[]>([]);

	// Channel type default form
	let showDefaultForm = $state(false);
	let editingDefaultId = $state<number | null>(null);
	let dfChannelType = $state('text');
	let dfEventType = $state('*');
	let dfXpMult = $state(1.0);
	let dfStarMult = $state(1.0);

	// Channel override form
	let showOverrideForm = $state(false);
	let editingOverrideId = $state<number | null>(null);
	let ovChannelId = $state('');
	let ovEventType = $state('*');
	let ovXpMult = $state(1.0);
	let ovStarMult = $state(1.0);
	let ovReason = $state('');
	let channelSearch = $state('');

	// Confirm delete
	let confirmOpen = $state(false);
	let confirmDeleteType = $state<'default' | 'override'>('default');
	let confirmDeleteId = $state<number | null>(null);

	const CHANNEL_TYPES = ['text', 'voice', 'forum', 'stage', 'announcement', 'category'];

	/** All event types + wildcard */
	const EVENT_OPTIONS = ['*', ...INTERACTION_TYPES];

	/** Filtered channels for search */
	let filteredChannels = $derived.by(() => {
		if (!channelSearch.trim()) return channels.filter(c => c.type !== 'category');
		const q = channelSearch.toLowerCase();
		return channels.filter(c => c.type !== 'category' && c.name.toLowerCase().includes(q));
	});

	/** Look up channel name by ID */
	function channelName(id: string): string {
		return channels.find(c => c.id === id)?.name ?? `#${id}`;
	}

	/** Grouped defaults by channel_type */
	let groupedDefaults = $derived.by(() => {
		const groups = new Map<string, TypeDefault[]>();
		for (const d of defaults) {
			if (!groups.has(d.channel_type)) groups.set(d.channel_type, []);
			groups.get(d.channel_type)!.push(d);
		}
		return groups;
	});

	/** Grouped overrides by channel */
	let groupedOverrides = $derived.by(() => {
		const groups = new Map<string, ChannelOverrideRow[]>();
		for (const o of overrides) {
			const name = channelName(o.channel_id);
			if (!groups.has(name)) groups.set(name, []);
			groups.get(name)!.push(o);
		}
		return groups;
	});

	// ---------------------------------------------------------------------------
	// Data loading
	// ---------------------------------------------------------------------------
	onMount(loadAll);

	async function loadAll() {
		loading = true;
		try {
			const [dRes, oRes, chRes] = await Promise.all([
				api.admin.getChannelDefaults(),
				api.admin.getChannelOverrides(),
				api.admin.getChannels(),
			]);
			defaults = dRes.defaults;
			overrides = oRes.overrides;
			channels = chRes.channels;
		} catch (e) {
			flash.error('Failed to load reward rules');
		} finally {
			loading = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Default CRUD
	// ---------------------------------------------------------------------------
	function openDefaultForm(row?: TypeDefault) {
		if (row) {
			editingDefaultId = row.id;
			dfChannelType = row.channel_type;
			dfEventType = row.event_type;
			dfXpMult = row.xp_multiplier;
			dfStarMult = row.star_multiplier;
		} else {
			editingDefaultId = null;
			dfChannelType = 'text';
			dfEventType = '*';
			dfXpMult = 1.0;
			dfStarMult = 1.0;
		}
		showDefaultForm = true;
	}

	async function saveDefault() {
		const payload: TypeDefaultUpsert = {
			channel_type: dfChannelType,
			event_type: dfEventType,
			xp_multiplier: dfXpMult,
			star_multiplier: dfStarMult,
		};
		try {
			await api.admin.upsertChannelDefault(payload);
			flash.success('Channel type default saved');
			showDefaultForm = false;
			await loadAll();
		} catch (e) {
			flash.error('Failed to save default');
		}
	}

	// ---------------------------------------------------------------------------
	// Override CRUD
	// ---------------------------------------------------------------------------
	function openOverrideForm(row?: ChannelOverrideRow) {
		if (row) {
			editingOverrideId = row.id;
			ovChannelId = row.channel_id;
			ovEventType = row.event_type;
			ovXpMult = row.xp_multiplier;
			ovStarMult = row.star_multiplier;
			ovReason = row.reason ?? '';
		} else {
			editingOverrideId = null;
			ovChannelId = '';
			ovEventType = '*';
			ovXpMult = 1.0;
			ovStarMult = 1.0;
			ovReason = '';
		}
		showOverrideForm = true;
		channelSearch = '';
	}

	async function saveOverride() {
		if (!ovChannelId) {
			flash.error('Please select a channel');
			return;
		}
		const payload: ChannelOverrideUpsert = {
			channel_id: ovChannelId,
			event_type: ovEventType,
			xp_multiplier: ovXpMult,
			star_multiplier: ovStarMult,
			reason: ovReason || undefined,
		};
		try {
			await api.admin.upsertChannelOverride(payload);
			flash.success('Channel override saved');
			showOverrideForm = false;
			await loadAll();
		} catch (e) {
			flash.error('Failed to save override');
		}
	}

	// ---------------------------------------------------------------------------
	// Delete
	// ---------------------------------------------------------------------------
	function confirmDelete(type: 'default' | 'override', id: number) {
		confirmDeleteType = type;
		confirmDeleteId = id;
		confirmOpen = true;
	}

	async function executeDelete() {
		if (confirmDeleteId === null) return;
		try {
			if (confirmDeleteType === 'default') {
				await api.admin.deleteChannelDefault(confirmDeleteId);
			} else {
				await api.admin.deleteChannelOverride(confirmDeleteId);
			}
			flash.success(`${confirmDeleteType === 'default' ? 'Default' : 'Override'} deleted`);
			await loadAll();
		} catch (e) {
			flash.error('Failed to delete');
		} finally {
			confirmOpen = false;
			confirmDeleteId = null;
		}
	}

	/** Format multiplier for display */
	function fmtMult(v: number): string {
		return v === 1.0 ? '1.0×' : `${v.toFixed(2)}×`;
	}

	/** Badge color based on multiplier */
	function multClass(v: number): string {
		if (v > 1.0) return 'text-green-400';
		if (v < 1.0) return 'text-red-400';
		return 'text-zinc-400';
	}
</script>

<svelte:head><title>Admin: Reward Rules — Synapse</title></svelte:head>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else}
<div class="max-w-5xl mx-auto space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold text-white">Reward Rules</h1>
	</div>

	<p class="text-sm text-zinc-400">
		Control how much {currency.primary} and {currency.secondary} are earned per channel type or for specific channels.
		Type defaults apply to all channels of that type; overrides let you customize individual channels.
	</p>

	<!-- Tabs -->
	<div class="flex border-b border-surface-300">
		<button
			class="px-4 py-2 text-sm font-medium transition-colors"
			class:text-brand-400={activeTab === 'defaults'}
			class:border-b-2={activeTab === 'defaults'}
			class:border-brand-400={activeTab === 'defaults'}
			class:text-zinc-400={activeTab !== 'defaults'}
			onclick={() => activeTab = 'defaults'}
		>
			Type Defaults ({defaults.length})
		</button>
		<button
			class="px-4 py-2 text-sm font-medium transition-colors"
			class:text-brand-400={activeTab === 'overrides'}
			class:border-b-2={activeTab === 'overrides'}
			class:border-brand-400={activeTab === 'overrides'}
			class:text-zinc-400={activeTab !== 'overrides'}
			onclick={() => activeTab = 'overrides'}
		>
			Channel Overrides ({overrides.length})
		</button>
	</div>

	<!-- ===== TYPE DEFAULTS TAB ===== -->
	{#if activeTab === 'defaults'}
		<div class="flex justify-end">
			<button class="btn-primary text-sm" onclick={() => openDefaultForm()}>
				+ Add Type Default
			</button>
		</div>

		{#if defaults.length === 0}
			<EmptyState
				title="No type defaults configured"
				description="Channel type defaults set base multipliers for all channels of a given type (text, voice, forum, etc.)."
			/>
		{:else}
			<div class="space-y-4">
				{#each [...groupedDefaults.entries()] as [chType, rows]}
					<div class="bg-surface-200/30 border border-surface-300 rounded-lg overflow-hidden">
						<div class="px-4 py-3 border-b border-surface-300 flex items-center gap-2">
							<span class="text-sm font-semibold text-white capitalize">{chType}</span>
							<span class="text-[10px] text-zinc-500 uppercase">channel type</span>
						</div>
						<div class="divide-y divide-surface-300">
							{#each rows as row (row.id)}
								<div class="px-4 py-3 flex items-center justify-between hover:bg-surface-200/50 transition-colors">
									<div class="flex items-center gap-4">
										<span class="text-sm text-zinc-300 font-mono w-36">
											{row.event_type === '*' ? 'All Events' : row.event_type}
										</span>
										<span class="text-sm {multClass(row.xp_multiplier)}">{currency.primary}: {fmtMult(row.xp_multiplier)}</span>
										<span class="text-sm {multClass(row.star_multiplier)}">{currency.secondary}: {fmtMult(row.star_multiplier)}</span>
									</div>
									<div class="flex gap-2">
										<button class="text-xs text-zinc-400 hover:text-white transition-colors" onclick={() => openDefaultForm(row)}>Edit</button>
										<button class="text-xs text-red-400 hover:text-red-300 transition-colors" onclick={() => confirmDelete('default', row.id)}>Delete</button>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}

	<!-- ===== CHANNEL OVERRIDES TAB ===== -->
	{:else}
		<div class="flex justify-end">
			<button class="btn-primary text-sm" onclick={() => openOverrideForm()}>
				+ Add Channel Override
			</button>
		</div>

		{#if overrides.length === 0}
			<EmptyState
				title="No channel overrides"
				description="Channel overrides let you customize multipliers for specific channels, overriding the type defaults."
			/>
		{:else}
			<div class="space-y-4">
				{#each [...groupedOverrides.entries()] as [chName, rows]}
					<div class="bg-surface-200/30 border border-surface-300 rounded-lg overflow-hidden">
						<div class="px-4 py-3 border-b border-surface-300 flex items-center gap-2">
							<span class="text-sm font-semibold text-white">#{chName}</span>
							<span class="text-[10px] text-zinc-500 uppercase">channel override</span>
						</div>
						<div class="divide-y divide-surface-300">
							{#each rows as row (row.id)}
								<div class="px-4 py-3 flex items-center justify-between hover:bg-surface-200/50 transition-colors">
									<div class="flex items-center gap-4">
										<span class="text-sm text-zinc-300 font-mono w-36">
											{row.event_type === '*' ? 'All Events' : row.event_type}
										</span>
										<span class="text-sm {multClass(row.xp_multiplier)}">{currency.primary}: {fmtMult(row.xp_multiplier)}</span>
										<span class="text-sm {multClass(row.star_multiplier)}">{currency.secondary}: {fmtMult(row.star_multiplier)}</span>
										{#if row.reason}
											<span class="text-xs text-zinc-500 italic truncate max-w-48" title={row.reason}>{row.reason}</span>
										{/if}
									</div>
									<div class="flex gap-2">
										<button class="text-xs text-zinc-400 hover:text-white transition-colors" onclick={() => openOverrideForm(row)}>Edit</button>
										<button class="text-xs text-red-400 hover:text-red-300 transition-colors" onclick={() => confirmDelete('override', row.id)}>Delete</button>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>
{/if}

<!-- ===== TYPE DEFAULT FORM MODAL ===== -->
{#if showDefaultForm}
	<div class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" role="dialog">
		<div class="bg-surface-100 border border-surface-300 rounded-xl w-full max-w-md p-6 space-y-4">
			<h3 class="text-lg font-bold text-white">
				{editingDefaultId ? 'Edit' : 'Add'} Type Default
			</h3>

			<div>
				<label class="block text-xs text-zinc-400 mb-1">
					Channel Type
					<select bind:value={dfChannelType} class="input w-full mt-0.5">
						{#each CHANNEL_TYPES as ct}
							<option value={ct}>{ct}</option>
						{/each}
					</select>
				</label>
			</div>

			<div>
				<label class="block text-xs text-zinc-400 mb-1">
					Event Type
					<select bind:value={dfEventType} class="input w-full mt-0.5">
						{#each EVENT_OPTIONS as et}
							<option value={et}>{et === '*' ? 'All Events (*)' : et}</option>
						{/each}
					</select>
				</label>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-zinc-400 mb-1">
						{currency.primary} Multiplier
						<input type="number" step="0.01" min="0" bind:value={dfXpMult} class="input w-full mt-0.5" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-zinc-400 mb-1">
						{currency.secondary} Multiplier
						<input type="number" step="0.01" min="0" bind:value={dfStarMult} class="input w-full mt-0.5" />
					</label>
				</div>
			</div>

			<div class="flex justify-end gap-2 pt-2">
				<button class="btn-secondary text-sm" onclick={() => showDefaultForm = false}>Cancel</button>
				<button class="btn-primary text-sm" onclick={saveDefault}>Save</button>
			</div>
		</div>
	</div>
{/if}

<!-- ===== CHANNEL OVERRIDE FORM MODAL ===== -->
{#if showOverrideForm}
	<div class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" role="dialog">
		<div class="bg-surface-100 border border-surface-300 rounded-xl w-full max-w-md p-6 space-y-4">
			<h3 class="text-lg font-bold text-white">
				{editingOverrideId ? 'Edit' : 'Add'} Channel Override
			</h3>

			<div>
			{#if editingOverrideId}
				<label class="block text-xs text-zinc-400 mb-1" for="channel-display">Channel</label>
				<div id="channel-display" class="input w-full bg-surface-200/50 text-zinc-300">#{channelName(ovChannelId)}</div>
			{:else}
				<label class="block text-xs text-zinc-400 mb-1" for="channel-search">Channel</label>
					<div id="channel-search" class="max-h-40 overflow-y-auto border border-surface-300 rounded bg-surface-200/30">
						{#each filteredChannels as ch (ch.id)}
							<button
								class="w-full px-3 py-1.5 text-left text-sm hover:bg-surface-200/50 transition-colors flex items-center justify-between {ovChannelId === ch.id ? 'bg-brand-500/20' : ''}"
								onclick={() => ovChannelId = ch.id}
							>
								<span class="text-zinc-200">#{ch.name}</span>
								<span class="text-[10px] text-zinc-500">{ch.type}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<div>
				<label class="block text-xs text-zinc-400 mb-1">
					Event Type
					<select bind:value={ovEventType} class="input w-full mt-0.5">
						{#each EVENT_OPTIONS as et}
							<option value={et}>{et === '*' ? 'All Events (*)' : et}</option>
						{/each}
					</select>
				</label>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-zinc-400 mb-1">
						{currency.primary} Multiplier
						<input type="number" step="0.01" min="0" bind:value={ovXpMult} class="input w-full mt-0.5" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-zinc-400 mb-1">
						{currency.secondary} Multiplier
						<input type="number" step="0.01" min="0" bind:value={ovStarMult} class="input w-full mt-0.5" />
					</label>
				</div>
			</div>

			<div>
				<label class="block text-xs text-zinc-400 mb-1">
					Reason (optional)
					<input type="text" bind:value={ovReason} placeholder="e.g. Double XP weekend channel" class="input w-full mt-0.5" />
				</label>
			</div>

			<div class="flex justify-end gap-2 pt-2">
				<button class="btn-secondary text-sm" onclick={() => showOverrideForm = false}>Cancel</button>
				<button class="btn-primary text-sm" onclick={saveOverride}>Save</button>
			</div>
		</div>
	</div>
{/if}

<!-- Confirm Delete Modal -->
<ConfirmModal
	bind:open={confirmOpen}
	title="Delete {confirmDeleteType === 'default' ? 'Type Default' : 'Channel Override'}?"
	message="This will remove the multiplier rule. Channels will fall back to the next matching rule or system defaults (1.0×)."
	confirmLabel="Delete"
	onconfirm={executeDelete}
	oncancel={() => {}}
/>
