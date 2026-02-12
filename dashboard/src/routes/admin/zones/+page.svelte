<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type AdminZone, type ZoneCreatePayload } from '$lib/api';
	import { flash } from '$lib/stores/flash';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';

	let zones = $state<AdminZone[]>([]);
	let loading = $state(true);
	let showCreate = $state(false);
	let editingId = $state<number | null>(null);

	// Form state
	let formName = $state('');
	let formDesc = $state('');
	let formChannels = $state('');

	// Confirm deactivation
	let confirmOpen = $state(false);
	let confirmZoneId = $state<number | null>(null);

	/** Zone icons by name pattern */
	const ZONE_ICONS: Record<string, string> = {
		programming: '💻', coding: '💻', dev: '💻', code: '💻',
		general: '💬', chat: '💬', social: '💬',
		memes: '😂', fun: '🎉', lounge: '🛋️',
		study: '📚', homework: '📝', academic: '🎓',
		gaming: '🎮', games: '🎮',
		music: '🎵', art: '🎨', creative: '✨',
		voice: '🔊', vc: '🔊',
		announcements: '📢', news: '📰',
		help: '❓', support: '🆘',
	};

	function getZoneIcon(name: string): string {
		const lower = name.toLowerCase();
		for (const [key, icon] of Object.entries(ZONE_ICONS)) {
			if (lower.includes(key)) return icon;
		}
		return '🗺️';
	}

	async function load() {
		try {
			const res = await api.admin.getZones();
			zones = res.zones;
		} catch (e) {
			flash.error('Failed to load zones');
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function resetForm() {
		formName = '';
		formDesc = '';
		formChannels = '';
		showCreate = false;
		editingId = null;
	}

	function startEdit(z: AdminZone) {
		editingId = z.id;
		formName = z.name;
		formDesc = z.description || '';
		formChannels = z.channel_ids.join(', ');
		showCreate = false;
	}

	async function handleCreate() {
		if (!formName.trim()) { flash.warning('Name is required'); return; }
		try {
			const channelIds = formChannels
				.split(',')
				.map((s) => s.trim())
				.filter(Boolean)
				.map(Number)
				.filter((n) => !isNaN(n));

			await api.admin.createZone({
				name: formName.trim(),
				description: formDesc.trim() || undefined,
				channel_ids: channelIds.length > 0 ? channelIds : undefined,
			});
			flash.success(`Zone "${formName}" created`);
			resetForm();
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Create failed');
		}
	}

	async function handleUpdate() {
		if (editingId === null) return;
		try {
			const channelIds = formChannels
				.split(',')
				.map((s) => s.trim())
				.filter(Boolean)
				.map(Number)
				.filter((n) => !isNaN(n));

			await api.admin.updateZone(editingId, {
				name: formName.trim() || undefined,
				description: formDesc.trim() || undefined,
				channel_ids: channelIds.length > 0 ? channelIds : undefined,
			});
			flash.success('Zone updated');
			resetForm();
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Update failed');
		}
	}

	function promptDeactivate(id: number) {
		confirmZoneId = id;
		confirmOpen = true;
	}

	async function deactivateZone() {
		if (confirmZoneId === null) return;
		try {
			await api.admin.updateZone(confirmZoneId, { active: false });
			flash.success('Zone deactivated');
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Deactivation failed');
		}
	}

	async function reactivateZone(id: number) {
		try {
			await api.admin.updateZone(id, { active: true });
			flash.success('Zone reactivated');
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Reactivation failed');
		}
	}

	/** Format a raw channel ID into a more readable form */
	function fmtChannelId(id: string): string {
		// Show abbreviated form like #···4567
		if (id.length > 6) {
			return `#···${id.slice(-4)}`;
		}
		return `#${id}`;
	}
</script>

<svelte:head><title>Admin: Zones — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">🗺️ Zones</h1>
		<p class="text-sm text-zinc-500 mt-1">Channel groupings with custom XP multipliers.</p>
	</div>
	<button class="btn-primary" onclick={() => { resetForm(); showCreate = !showCreate; }}>
		+ New Zone
	</button>
</div>

<!-- Create/Edit Form -->
{#if showCreate || editingId !== null}
	<div class="card mb-6 animate-slide-up">
		<h3 class="text-sm font-semibold text-zinc-300 mb-4">{editingId ? 'Edit Zone' : 'Create Zone'}</h3>
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
			<div>
				<label class="label" for="zone-name">Name</label>
				<input id="zone-name" class="input" bind:value={formName} placeholder="e.g. study-hall" />
			</div>
			<div>
				<label class="label" for="zone-channels">Channel IDs (comma-separated)</label>
				<input id="zone-channels" class="input" bind:value={formChannels} placeholder="123456, 789012" />
			</div>
			<div class="sm:col-span-2">
				<label class="label" for="zone-desc">Description</label>
				<input id="zone-desc" class="input" bind:value={formDesc} placeholder="Optional description" />
			</div>
		</div>
		<div class="flex gap-2 mt-4">
			{#if editingId}
				<button class="btn-primary" onclick={handleUpdate}>Save Changes</button>
			{:else}
				<button class="btn-primary" onclick={handleCreate}>Create Zone</button>
			{/if}
			<button class="btn-secondary" onclick={resetForm}>Cancel</button>
		</div>
	</div>
{/if}

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if zones.length === 0}
	<EmptyState
		icon="🗺️"
		title="No zones configured"
		description="Zones group Discord channels with custom XP multipliers. Create your first zone to start shaping the reward landscape."
		action={{ label: '+ Create Zone', onclick: () => { resetForm(); showCreate = true; } }}
	/>
{:else}
	<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
		{#each zones as zone (zone.id)}
			<div class="card card-hover group {!zone.active ? 'opacity-50' : ''}">
				<div class="flex items-start gap-4">
					<!-- Zone icon -->
					<div class="w-12 h-12 rounded-xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-2xl flex-shrink-0">
						{getZoneIcon(zone.name)}
					</div>

					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2 mb-1">
							<h3 class="text-sm font-semibold text-white">{zone.name}</h3>
							{#if !zone.active}
								<span class="badge bg-red-500/10 text-red-400 border border-red-500/20">Inactive</span>
							{:else}
								<span class="badge bg-green-500/10 text-green-400 border border-green-500/20">Active</span>
							{/if}
						</div>
						{#if zone.description}
							<p class="text-xs text-zinc-500 mb-2">{zone.description}</p>
						{/if}

						<!-- Channel tags -->
						{#if zone.channel_ids.length > 0}
							<div class="flex flex-wrap gap-1.5 mb-2">
								{#each zone.channel_ids as ch}
									<span
										class="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md
											bg-surface-200 text-zinc-400 border border-surface-300
											hover:bg-surface-300 hover:text-zinc-300 transition-colors cursor-default"
										title="Channel ID: {ch}"
									>
										<svg class="w-3 h-3 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
											<path stroke-linecap="round" stroke-linejoin="round" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
										</svg>
										{fmtChannelId(ch)}
									</span>
								{/each}
							</div>
						{:else}
							<p class="text-[11px] text-zinc-600 italic mb-2">No channels assigned</p>
						{/if}

						<!-- Multipliers -->
						{#if Object.keys(zone.multipliers).length > 0}
							<div class="flex flex-wrap gap-2">
								{#each Object.entries(zone.multipliers) as [type, mult]}
									<div class="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md bg-brand-500/10 border border-brand-500/20">
										<span class="text-brand-400 font-semibold">{type}</span>
										<span class="text-zinc-500">·</span>
										<span class="text-brand-300 font-mono">{mult.xp}× XP</span>
										{#if mult.star > 0}
											<span class="text-gold-400 font-mono">{mult.star}× ★</span>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</div>

				<!-- Actions (visible on hover) -->
				<div class="flex gap-2 mt-4 pt-3 border-t border-surface-300/50 opacity-0 group-hover:opacity-100 transition-opacity">
					<button class="btn-secondary text-xs" onclick={() => startEdit(zone)}>✏️ Edit</button>
					{#if zone.active}
						<button class="btn-danger text-xs" onclick={() => promptDeactivate(zone.id)}>Deactivate</button>
					{:else}
						<button class="btn-secondary text-xs" onclick={() => reactivateZone(zone.id)}>✅ Reactivate</button>
					{/if}
				</div>
			</div>
		{/each}
	</div>
{/if}

<ConfirmModal
	bind:open={confirmOpen}
	title="Deactivate Zone?"
	message="This zone will be hidden but not deleted. You can reactivate it later."
	confirmLabel="Deactivate"
	danger
	onconfirm={deactivateZone}
	oncancel={() => { confirmZoneId = null; }}
/>
