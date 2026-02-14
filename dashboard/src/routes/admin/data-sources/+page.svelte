<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type DataSourceConfig, type EventLakeHealth, type StorageEstimate } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { fmtShort, fmtDateTime, timeAgo } from '$lib/utils';

	let sources = $state<DataSourceConfig[]>([]);
	let health = $state<EventLakeHealth | null>(null);
	let storage = $state<StorageEstimate | null>(null);
	let loading = $state(true);
	let saving = $state(false);
	let pendingToggles = $state<Record<string, boolean>>({});

	// Operation states
	let runningRetention = $state(false);
	let runningReconciliation = $state(false);
	let runningBackfill = $state(false);

	/** Event type icons */
	const TYPE_ICONS: Record<string, string> = {
		message_create: '',
		reaction_add: '',
		reaction_remove: '',
		thread_create: '',
		voice_join: '',
		voice_leave: '',
		voice_move: '',
		member_join: '',
		member_leave: '',
	};

	/** Event type colors for volume bars */
	const TYPE_COLORS: Record<string, string> = {
		message_create: '#7c3aed',
		reaction_add: '#2196f3',
		reaction_remove: '#ef4444',
		thread_create: '#ff9800',
		voice_join: '#10b981',
		voice_leave: '#f59e0b',
		voice_move: '#06b6d4',
		member_join: '#8b5cf6',
		member_leave: '#ec4899',
	};

	async function load() {
		try {
			const [s, h, st] = await Promise.all([
				api.admin.getDataSources(),
				api.admin.getEventLakeHealth(30),
				api.admin.getStorageEstimate(),
			]);
			sources = s;
			health = h;
			storage = st;
			pendingToggles = {};
		} catch (e: any) {
			flash.error(e.message || 'Failed to load Event Lake data');
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function toggleSource(eventType: string, enabled: boolean) {
		pendingToggles[eventType] = enabled;
		pendingToggles = { ...pendingToggles };
	}

	function isEnabled(ds: DataSourceConfig): boolean {
		if (ds.event_type in pendingToggles) return pendingToggles[ds.event_type];
		return ds.enabled;
	}

	const hasChanges = $derived(Object.keys(pendingToggles).length > 0);

	async function saveToggles() {
		saving = true;
		try {
			const toggles = Object.entries(pendingToggles).map(([event_type, enabled]) => ({
				event_type, enabled,
			}));
			await api.admin.toggleDataSources(toggles);
			flash.success(`${toggles.length} data source(s) updated`);
			await load();
		} catch (e: any) {
			flash.error(e.message);
		} finally {
			saving = false;
		}
	}

	async function runRetention() {
		runningRetention = true;
		try {
			const result = await api.admin.triggerRetention(90);
			flash.success(`Retention: ${result.events_deleted} events, ${result.counters_deleted} counters removed`);
			await load();
		} catch (e: any) { flash.error(e.message); }
		finally { runningRetention = false; }
	}

	async function runReconciliation() {
		runningReconciliation = true;
		try {
			const result = await api.admin.triggerReconciliation();
			flash.success(`Reconciliation: checked ${result.checked}, corrected ${result.corrected}`);
		} catch (e: any) { flash.error(e.message); }
		finally { runningReconciliation = false; }
	}

	async function runBackfill() {
		runningBackfill = true;
		try {
			const result = await api.admin.triggerBackfill(false);
			flash.success(`Backfill: ${result.counters_upserted} counters upserted from ${result.rows_read} activity rows`);
			await load();
		} catch (e: any) { flash.error(e.message); }
		finally { runningBackfill = false; }
	}

	function formatBytes(bytes: number): string {
		if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
		if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
		if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${bytes} B`;
	}

	// Compute max volume for bar scaling
	const maxVolume = $derived(
		health ? Math.max(...Object.values(health.volume_by_type), 1) : 1
	);
</script>

<svelte:head><title>Admin: Data Sources — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">Event Lake</h1>
		<p class="text-sm text-zinc-500 mt-1">Configure data sources, monitor volume, and manage storage.</p>
	</div>
	{#if hasChanges}
		<button class="btn-primary" onclick={saveToggles} disabled={saving}>
			{#if saving}
				<span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
				Saving…
			{:else}
				Save Changes
			{/if}
		</button>
	{/if}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else}

	<!-- Health Overview Cards -->
	{#if health}
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
			<div class="card p-4">
				<p class="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Total Events</p>
				<p class="text-2xl font-bold text-white mt-1">{fmtShort(health.total_events)}</p>
			</div>
			<div class="card p-4">
				<p class="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Today <span class="normal-case opacity-60">(UTC)</span></p>
				<p class="text-2xl font-bold text-white mt-1">{fmtShort(health.events_today)}</p>
			</div>
			<div class="card p-4">
				<p class="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Last 7 Days</p>
				<p class="text-2xl font-bold text-white mt-1">{fmtShort(health.events_7d)}</p>
			</div>
			<div class="card p-4">
				<p class="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Table Size</p>
				<p class="text-2xl font-bold text-white mt-1">{formatBytes(health.table_size_bytes)}</p>
			</div>
		</div>
	{/if}

	<!-- Data Sources Grid -->
	<div class="settings-group mb-8">
		<div class="settings-group-header flex items-center gap-3">
			
			<div>
				<h3 class="text-sm font-semibold text-zinc-200">Data Sources</h3>
				<p class="text-xs text-zinc-500">Toggle which Discord events are captured to the Event Lake.</p>
			</div>
		</div>
		<div class="divide-y divide-surface-300/30">
			{#each sources as ds (ds.event_type)}
				{@const enabled = isEnabled(ds)}
				{@const volume = health?.volume_by_type[ds.event_type] ?? 0}
				{@const barWidth = maxVolume > 0 ? (volume / maxVolume) * 100 : 0}
				<div class="flex items-center gap-4 px-5 py-4 hover:bg-surface-200/30 transition-colors
					{ds.event_type in pendingToggles ? 'bg-brand-500/5 border-l-2 border-l-brand-500' : ''}">
					<!-- Icon & info -->
					<span class="text-xl w-8 text-center"></span>
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2">
							<span class="text-sm font-medium text-zinc-200">{ds.label}</span>
							{#if !enabled}
								<span class="badge bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 text-[10px]">Disabled</span>
							{/if}
						</div>
						<p class="text-[10px] text-zinc-500 mt-0.5">{ds.description}</p>
						<!-- Volume bar -->
						{#if volume > 0}
							<div class="mt-2 flex items-center gap-2">
								<div class="flex-1 h-1.5 bg-surface-300 rounded-full overflow-hidden">
									<div class="h-full rounded-full transition-all duration-500"
										style="width: {barWidth}%; background: {TYPE_COLORS[ds.event_type] ?? '#71717a'}"></div>
								</div>
								<span class="text-[10px] text-zinc-500 font-mono w-16 text-right">{fmtShort(volume)}</span>
							</div>
						{/if}
					</div>
					<!-- Toggle -->
					<button
						class="relative w-11 h-6 rounded-full transition-colors duration-200
							{enabled ? 'bg-brand-600' : 'bg-surface-300'}"
						onclick={() => toggleSource(ds.event_type, !enabled)}
						role="switch"
						aria-checked={enabled}
						aria-label={`Toggle ${ds.label}`}
					>
						<span class="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200
							{enabled ? 'translate-x-5' : ''}"></span>
					</button>
				</div>
			{/each}
		</div>
	</div>

	<!-- Storage Estimate -->
	{#if storage}
		<div class="settings-group mb-8">
			<div class="settings-group-header flex items-center gap-3">
				
				<div>
					<h3 class="text-sm font-semibold text-zinc-200">Storage Estimate</h3>
					<p class="text-xs text-zinc-500">Based on ~{storage.avg_row_bytes} bytes per event row.</p>
				</div>
			</div>
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 p-5">
				<div>
					<p class="text-[10px] text-zinc-500 uppercase tracking-wider">Current Size</p>
					<p class="text-lg font-bold text-white">{storage.estimated_mb} MB</p>
				</div>
				<div>
					<p class="text-[10px] text-zinc-500 uppercase tracking-wider">Daily Rate</p>
					<p class="text-lg font-bold text-white">{storage.daily_rate} rows/day</p>
				</div>
				<div>
					<p class="text-[10px] text-zinc-500 uppercase tracking-wider">Days of Data</p>
					<p class="text-lg font-bold text-white">{storage.days_of_data}</p>
				</div>
				<div>
					<p class="text-[10px] text-zinc-500 uppercase tracking-wider">Projected 90d</p>
					<p class="text-lg font-bold text-white">{storage.projected_90d_mb} MB</p>
				</div>
			</div>
		</div>
	{/if}

	<!-- Time Range Info -->
	{#if health}
		<div class="settings-group mb-8">
			<div class="settings-group-header flex items-center gap-3">
				
				<div>
					<h3 class="text-sm font-semibold text-zinc-200">Data Range</h3>
					<p class="text-xs text-zinc-500">Time span of stored events.</p>
				</div>
			</div>
			<div class="grid grid-cols-2 gap-4 p-5">
				<div>
					<p class="text-[10px] text-zinc-500 uppercase tracking-wider">Oldest Event</p>
					<p class="text-sm text-zinc-200">{health.oldest_event ? fmtDateTime(health.oldest_event) : 'No events'}</p>
					{#if health.oldest_event}
						<p class="text-[10px] text-zinc-500">{timeAgo(health.oldest_event)}</p>
					{/if}
				</div>
				<div>
					<p class="text-[10px] text-zinc-500 uppercase tracking-wider">Newest Event</p>
					<p class="text-sm text-zinc-200">{health.newest_event ? fmtDateTime(health.newest_event) : 'No events'}</p>
					{#if health.newest_event}
						<p class="text-[10px] text-zinc-500">{timeAgo(health.newest_event)}</p>
					{/if}
				</div>
			</div>
		</div>
	{/if}

	<!-- Maintenance Operations -->
	<div class="settings-group mb-8 danger-zone">
		<div class="settings-group-header flex items-center gap-3">
			
			<div>
				<h3 class="text-sm font-semibold text-zinc-200">Maintenance</h3>
				<p class="text-xs text-zinc-500">Manual triggers for Event Lake maintenance jobs.</p>
			</div>
			<span class="ml-auto badge bg-red-500/10 text-red-400 border border-red-500/20">⚠ Admin</span>
		</div>
		<div class="divide-y divide-surface-300/30">
			<!-- Retention -->
			<div class="flex items-center justify-between px-5 py-4">
				<div>
					<p class="text-sm font-medium text-zinc-200">Run Retention Cleanup</p>
					<p class="text-[10px] text-zinc-500">Delete events older than 90 days and prune stale day-counters.</p>
				</div>
				<button class="btn-secondary text-xs" onclick={runRetention} disabled={runningRetention}>
					{runningRetention ? 'Running…' : 'Run Now'}
				</button>
			</div>
			<!-- Reconciliation -->
			<div class="flex items-center justify-between px-5 py-4">
				<div>
					<p class="text-sm font-medium text-zinc-200">Reconcile Counters</p>
					<p class="text-[10px] text-zinc-500">Validate lifetime counters against raw events and fix drift.</p>
				</div>
				<button class="btn-secondary text-xs" onclick={runReconciliation} disabled={runningReconciliation}>
					{runningReconciliation ? 'Running…' : 'Reconcile'}
				</button>
			</div>
			<!-- Backfill -->
			<div class="flex items-center justify-between px-5 py-4">
				<div>
					<p class="text-sm font-medium text-zinc-200">Backfill from Activity Log</p>
					<p class="text-[10px] text-zinc-500">Migrate legacy activity_log counts into event_counters (one-time).</p>
				</div>
				<button class="btn-secondary text-xs" onclick={runBackfill} disabled={runningBackfill}>
					{runningBackfill ? 'Running…' : 'Backfill'}
				</button>
			</div>
		</div>
	</div>

{/if}
