<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type MarketplaceItemRow,
		type MarketplaceItemCreate,
		type MarketplaceItemUpdate,
		type AchievementRarityItem,
		type MediaFileItem,
	} from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------
	let items = $state<MarketplaceItemRow[]>([]);
	let rarities = $state<AchievementRarityItem[]>([]);
	let loading = $state(true);
	let searchQuery = $state('');
	let filterActive = $state<'all' | 'active' | 'inactive'>('all');

	// Editor
	let showEditor = $state(false);
	let editingItem = $state<MarketplaceItemRow | null>(null);
	let saving = $state(false);

	let formName = $state('');
	let formDescription = $state('');
	let formItemType = $state('COSMETIC_BADGE');
	let formCostXp = $state<number | null>(null);
	let formCostGold = $state<number | null>(null);
	let formRarityId = $state<number | null>(null);
	let formOverlayId = $state<number | null>(null);
	let formImageUrl = $state<string | null>(null);
	let formDiscordRoleId = $state('');
	let formSeasonId = $state<number | null>(null);
	let formExpiresAt = $state('');
	let formActive = $state(true);

	// Delete
	let confirmDeactivateId = $state<number | null>(null);

	// Overlay picker
	let showOverlayPicker = $state(false);
	let overlayFiles = $state<MediaFileItem[]>([]);
	let overlayLoaded = $state(false);

	const ITEM_TYPES = [
		{ value: 'COSMETIC_BADGE', label: 'Cosmetic Badge' },
		{ value: 'COSMETIC_OVERLAY', label: 'Profile Overlay' },
		{ value: 'DISCORD_ROLE', label: 'Discord Role' },
		{ value: 'TITLE', label: 'Title' },
		{ value: 'CONSUMABLE', label: 'Consumable' },
	];

	// ---------------------------------------------------------------------------
	// Data loading
	// ---------------------------------------------------------------------------
	async function load() {
		try {
			const [itemsRes, rarRes] = await Promise.all([
				api.admin.getMarketplaceItems(),
				api.admin.getAchievementRarities(),
			]);
			items = itemsRes.items;
			rarities = rarRes.rarities;
		} catch (e: any) {
			flash.error(e.message || 'Failed to load marketplace items');
		} finally {
			loading = false;
		}
	}
	onMount(load);

	// ---------------------------------------------------------------------------
	// Filtering
	// ---------------------------------------------------------------------------
	let filteredItems = $derived.by(() => {
		let result = items;
		if (searchQuery) {
			const q = searchQuery.toLowerCase();
			result = result.filter(
				(i) => i.name.toLowerCase().includes(q) || (i.description ?? '').toLowerCase().includes(q)
			);
		}
		if (filterActive === 'active') result = result.filter((i) => i.active);
		if (filterActive === 'inactive') result = result.filter((i) => !i.active);
		return result;
	});

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------
	function rarityName(id: number | null): string {
		if (!id) return '—';
		return rarities.find((r) => r.id === id)?.name ?? '—';
	}
	function rarityColor(id: number | null): string {
		if (!id) return '#6b7280';
		return rarities.find((r) => r.id === id)?.color ?? '#6b7280';
	}
	function typeBadgeColor(type: string): string {
		switch (type) {
			case 'DISCORD_ROLE': return 'bg-indigo-500/20 text-indigo-400';
			case 'COSMETIC_OVERLAY': return 'bg-purple-500/20 text-purple-400';
			case 'COSMETIC_BADGE': return 'bg-blue-500/20 text-blue-400';
			case 'TITLE': return 'bg-amber-500/20 text-amber-400';
			case 'CONSUMABLE': return 'bg-green-500/20 text-green-400';
			default: return 'bg-zinc-500/20 text-zinc-400';
		}
	}
	function formatCost(item: MarketplaceItemRow): string {
		const parts: string[] = [];
		if (item.cost_xp) parts.push(`${item.cost_xp} ${currency.primary}`);
		if (item.cost_gold) parts.push(`${item.cost_gold} ${currency.secondary}`);
		return parts.length ? parts.join(' / ') : 'Free';
	}

	// ---------------------------------------------------------------------------
	// Editor
	// ---------------------------------------------------------------------------
	function openNew() {
		editingItem = null;
		formName = '';
		formDescription = '';
		formItemType = 'COSMETIC_BADGE';
		formCostXp = null;
		formCostGold = null;
		formRarityId = null;
		formOverlayId = null;
		formImageUrl = null;
		formDiscordRoleId = '';
		formSeasonId = null;
		formExpiresAt = '';
		formActive = true;
		showEditor = true;
	}

	function openEdit(item: MarketplaceItemRow) {
		editingItem = item;
		formName = item.name;
		formDescription = item.description ?? '';
		formItemType = item.item_type;
		formCostXp = item.cost_xp;
		formCostGold = item.cost_gold;
		formRarityId = item.rarity_id;
		formOverlayId = item.overlay_id;
		formImageUrl = item.image_url ?? null;
		formDiscordRoleId = item.discord_role_id ?? '';
		formSeasonId = item.season_id;
		formExpiresAt = item.expires_at ? item.expires_at.slice(0, 16) : '';
		formActive = item.active;
		showEditor = true;
	}

	async function saveItem() {
		if (!formName.trim()) { flash.warning('Name is required'); return; }
		saving = true;
		try {
			const discordRoleIdRaw = formDiscordRoleId.trim();
			const discordRoleId = discordRoleIdRaw
				? Number.parseInt(discordRoleIdRaw, 10)
				: null;
			if (discordRoleIdRaw && Number.isNaN(discordRoleId)) {
				flash.warning('Discord Role ID must be numeric');
				return;
			}

			if (editingItem) {
				const payload: MarketplaceItemUpdate = {
					name: formName.trim(),
					description: formDescription.trim() || undefined,
					item_type: formItemType,
					cost_xp: formCostXp,
					cost_gold: formCostGold,
					rarity_id: formRarityId,
					overlay_id: formOverlayId,
					image_url: formImageUrl,
					discord_role_id: discordRoleId,
					season_id: formSeasonId,
					active: formActive,
					expires_at: formExpiresAt || null,
				};
				await api.admin.updateMarketplaceItem(editingItem.id, payload);
				flash.success('Item updated');
			} else {
				const payload: MarketplaceItemCreate = {
					name: formName.trim(),
					description: formDescription.trim() || undefined,
					item_type: formItemType,
					cost_xp: formCostXp,
					cost_gold: formCostGold,
					rarity_id: formRarityId,
					overlay_id: formOverlayId,
					image_url: formImageUrl,
					discord_role_id: discordRoleId,
					season_id: formSeasonId,
					expires_at: formExpiresAt || null,
				};
				await api.admin.createMarketplaceItem(payload);
				flash.success('Item created');
			}
			showEditor = false;
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to save item');
		} finally {
			saving = false;
		}
	}

	async function deactivateItem(id: number) {
		try {
			await api.admin.deactivateMarketplaceItem(id);
			flash.success('Item deactivated');
			confirmDeactivateId = null;
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to deactivate item');
		}
	}

	async function toggleActive(item: MarketplaceItemRow) {
		try {
			await api.admin.updateMarketplaceItem(item.id, { active: !item.active });
			flash.success(item.active ? 'Item deactivated' : 'Item activated');
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to toggle item');
		}
	}

	// Overlay picker
	async function openOverlayPicker() {
		showOverlayPicker = true;
		if (!overlayLoaded) {
			try {
				const res = await api.admin.getMedia();
				overlayFiles = res.files;
				overlayLoaded = true;
			} catch { flash.error('Failed to load media'); }
		}
	}
</script>

<svelte:head>
	<title>Marketplace — Synapse Admin</title>
</svelte:head>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-white">Marketplace</h1>
			<p class="text-sm text-surface-400 mt-1">Manage shop items, pricing, and cosmetics</p>
		</div>
		<button class="btn-primary" onclick={openNew}>+ New Item</button>
	</div>

	{#if loading}
		<SynapseLoader />
	{:else}
		<!-- Filters -->
		<div class="flex items-center gap-3 flex-wrap">
			<input
				type="text"
				class="input flex-1 min-w-[200px]"
				placeholder="Search items..."
				bind:value={searchQuery}
			/>
			<div class="flex gap-1 bg-surface-300/10 p-1 rounded-lg">
				{#each [['all', 'All'], ['active', 'Active'], ['inactive', 'Inactive']] as [val, label]}
					<button
						class="px-3 py-1 text-xs rounded transition-colors {filterActive === val ? 'bg-brand-500 text-white' : 'text-surface-400 hover:text-white'}"
						onclick={() => filterActive = val as 'all' | 'active' | 'inactive'}
					>{label}</button>
				{/each}
			</div>
		</div>

		<!-- Items Grid -->
		{#if filteredItems.length === 0}
			<EmptyState
				title="No marketplace items"
				description={searchQuery ? 'No items match your search' : 'No marketplace items yet. Create one to get started.'}
			/>
		{:else}
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
				{#each filteredItems as item (item.id)}
					<div class="card p-4 flex flex-col gap-3 transition-opacity {item.active ? '' : 'opacity-60'}">
						<!-- Header -->
						<div class="flex items-start justify-between gap-2">
							<div class="min-w-0">
								<h3 class="font-semibold text-white truncate">{item.name}</h3>
								{#if item.description}
									<p class="text-xs text-surface-400 mt-0.5 line-clamp-2">{item.description}</p>
								{/if}
							</div>
							<button
								class="w-9 h-5 rounded-full shrink-0 transition-colors {item.active ? 'bg-green-500' : 'bg-surface-400/40'}"
								onclick={() => toggleActive(item)}
								title={item.active ? 'Active' : 'Inactive'}
							>
								<div class="w-3.5 h-3.5 rounded-full bg-white transition-transform {item.active ? 'translate-x-4' : 'translate-x-0.5'}"></div>
							</button>
						</div>

						<!-- Badges -->
						<div class="flex flex-wrap gap-1.5">
							<span class="text-xs px-2 py-0.5 rounded {typeBadgeColor(item.item_type)}">
								{ITEM_TYPES.find(t => t.value === item.item_type)?.label ?? item.item_type}
							</span>
							{#if item.rarity_id}
								<span class="text-xs px-2 py-0.5 rounded border" style="border-color: {rarityColor(item.rarity_id)}; color: {rarityColor(item.rarity_id)}">
									{rarityName(item.rarity_id)}
								</span>
							{/if}
							{#if item.discord_role_id}
								<span class="text-xs px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400">Role</span>
							{/if}
							{#if item.image_url}
								<img src={item.image_url} alt="Badge" class="w-5 h-5 object-contain rounded bg-surface-900" />
							{/if}
						</div>

						<!-- Cost -->
						<div class="text-sm font-medium">
							{#if item.cost_xp || item.cost_gold}
								<div class="flex gap-3">
									{#if item.cost_xp}
										<span class="text-brand-400">{item.cost_xp.toLocaleString()} {currency.primary}</span>
									{/if}
									{#if item.cost_gold}
										<span class="text-yellow-400">{item.cost_gold.toLocaleString()} {currency.secondary}</span>
									{/if}
								</div>
							{:else}
								<span class="text-surface-400">Free</span>
							{/if}
						</div>

						<!-- Meta -->
						<div class="flex items-center gap-2 text-xs text-surface-400 mt-auto">
							{#if item.expires_at}
								<span title="Expires">Exp: {new Date(item.expires_at).toLocaleDateString()}</span>
							{/if}
							{#if item.created_at}
								<span class="ml-auto">Created {new Date(item.created_at).toLocaleDateString()}</span>
							{/if}
						</div>

						<!-- Actions -->
						<div class="flex gap-2 pt-1 border-t border-surface-400/10">
							<button class="btn-secondary text-xs flex-1" onclick={() => openEdit(item)}>Edit</button>
							{#if item.active}
								<button
									class="text-xs px-3 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20"
									onclick={() => confirmDeactivateId = item.id}
								>Deactivate</button>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<!-- Item Editor Modal -->
{#if showEditor}
<div class="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 flex items-start justify-center pt-10 overflow-y-auto">
	<div class="card p-6 w-full max-w-xl mx-4 my-8 space-y-4">
		<h2 class="text-xl font-bold text-white">{editingItem ? 'Edit Item' : 'New Item'}</h2>

		<!-- Name -->
		<div>
			<label class="label" for="item-name">Name</label>
			<input id="item-name" type="text" class="input w-full" bind:value={formName} placeholder="e.g. Rare Profile Frame" />
		</div>

		<!-- Description -->
		<div>
			<label class="label" for="item-description">Description</label>
			<textarea id="item-description" class="input w-full" rows="2" bind:value={formDescription} placeholder="Optional description"></textarea>
		</div>

		<!-- Type + Active -->
		<div class="grid grid-cols-2 gap-4">
			<div>
				<label class="label" for="item-type">Item Type</label>
				<select id="item-type" class="input w-full" bind:value={formItemType}>
					{#each ITEM_TYPES as t}
						<option value={t.value}>{t.label}</option>
					{/each}
				</select>
			</div>
			<div>
				<div class="label">Status</div>
				<label class="flex items-center gap-2 mt-2 text-sm text-surface-300">
					<input type="checkbox" bind:checked={formActive} class="accent-brand-400" />
					Active (visible in shop)
				</label>
			</div>
		</div>

		<!-- Pricing -->
		<div class="grid grid-cols-2 gap-4">
			<div>
				<label class="label" for="item-cost-xp">Cost ({currency.primary})</label>
				<input id="item-cost-xp" type="number" class="input w-full" bind:value={formCostXp} placeholder="—" min="0" />
			</div>
			<div>
				<label class="label" for="item-cost-gold">Cost ({currency.secondary})</label>
				<input id="item-cost-gold" type="number" class="input w-full" bind:value={formCostGold} placeholder="—" min="0" />
			</div>
		</div>

		<!-- Rarity -->
		<div>
			<label class="label" for="item-rarity">Rarity</label>
			<select id="item-rarity" class="input w-full" bind:value={formRarityId}>
				<option value={null}>No rarity</option>
				{#each rarities as r}
					<option value={r.id}>{r.name}</option>
				{/each}
			</select>
		</div>

		<!-- Discord Role ID (for DISCORD_ROLE type) -->
		{#if formItemType === 'DISCORD_ROLE'}
			<div>
				<label class="label" for="item-role-id">Discord Role ID</label>
				<input id="item-role-id" type="text" class="input w-full" bind:value={formDiscordRoleId} placeholder="e.g. 123456789012345678" />
			</div>
		{/if}

		<!-- Overlay (for overlay type) -->
		{#if formItemType === 'COSMETIC_OVERLAY'}
			<div>
				<div class="label">Overlay Image</div>
				<div class="flex gap-2 items-center">
					{#if formOverlayId}
						<span class="text-sm text-green-400">Overlay #{formOverlayId}</span>
					{:else}
						<span class="text-sm text-surface-400">None selected</span>
					{/if}
					<button class="btn-secondary text-xs" onclick={openOverlayPicker}>Browse Media</button>
				</div>
			</div>
		{/if}

		<!-- Badge Image (for badge type) -->
		{#if formItemType === 'COSMETIC_BADGE'}
			<div>
				<div class="label">Badge Image</div>
				<div class="flex gap-2 items-center">
					{#if formImageUrl}
						<img src={formImageUrl} alt="Badge preview" class="w-8 h-8 object-contain rounded bg-surface-900" />
						<span class="text-sm text-green-400 truncate max-w-[200px]">{formImageUrl.split('/').pop()}</span>
					{:else}
						<span class="text-sm text-surface-400">None selected</span>
					{/if}
					<button class="btn-secondary text-xs" onclick={openOverlayPicker}>Browse Media</button>
				</div>
			</div>
		{/if}

		<!-- Expiry -->
		<div>
			<label class="label" for="item-expires-at">Expires At (optional)</label>
			<input id="item-expires-at" type="datetime-local" class="input w-full" bind:value={formExpiresAt} />
		</div>

		<!-- Actions -->
		<div class="flex justify-end gap-3 pt-2">
			<button class="btn-secondary" onclick={() => showEditor = false}>Cancel</button>
			<button class="btn-primary" onclick={saveItem} disabled={saving || !formName.trim()}>
				{saving ? 'Saving...' : (editingItem ? 'Update Item' : 'Create Item')}
			</button>
		</div>
	</div>
</div>
{/if}

<!-- Deactivate confirmation -->
{#if confirmDeactivateId !== null}
	<ConfirmModal
		open={true}
		title="Deactivate Item"
		message="This will remove the item from the shop. Users who already purchased it will keep it."
		confirmLabel="Deactivate"
		onconfirm={() => deactivateItem(confirmDeactivateId!)}
		oncancel={() => confirmDeactivateId = null}
	/>
{/if}

<!-- Overlay Picker Modal -->
{#if showOverlayPicker}
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
	role="dialog" aria-modal="true" aria-label="Select media image">
	<div class="bg-surface-800 border border-surface-600 rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
		<div class="flex items-center justify-between p-4 border-b border-surface-600">
			<h3 class="text-lg font-semibold text-white">Select Image</h3>
			<button class="text-zinc-400 hover:text-zinc-200" onclick={() => showOverlayPicker = false}>&times;</button>
		</div>
		<div class="p-4 overflow-y-auto flex-1">
			{#if overlayFiles.length === 0}
				<p class="text-zinc-500 text-center py-8">No media files. Upload images on the <a href="/admin/media" class="text-brand-400 underline">Media</a> page first.</p>
			{:else}
				<div class="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2">
					{#each overlayFiles as mf}
						<button type="button" class="group relative aspect-square rounded border border-surface-600
							hover:border-brand-400 overflow-hidden transition-colors focus:outline-none focus:ring-2 focus:ring-brand-400"
							onclick={() => { 
								if (formItemType === 'COSMETIC_OVERLAY') {
									formOverlayId = mf.id; 
								} else if (formItemType === 'COSMETIC_BADGE') {
									formImageUrl = mf.url;
								}
								showOverlayPicker = false; 
							}}>
							<img src={mf.url} alt={mf.alt_text || mf.original_name} class="w-full h-full object-cover" />
							<div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-end">
								<span class="text-[10px] text-white p-1 truncate w-full">{mf.original_name}</span>
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</div>
		<div class="p-3 border-t border-surface-600 flex justify-end">
			<button class="btn-secondary text-xs" onclick={() => showOverlayPicker = false}>Cancel</button>
		</div>
	</div>
</div>
{/if}
