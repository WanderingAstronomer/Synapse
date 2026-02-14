<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { api, type LogEntry } from '$lib/api';
	import { LOG_LEVELS } from '$lib/constants';
	import { flash } from '$lib/stores/flash.svelte';
	import AuditLogView from '$lib/components/AuditLogView.svelte';

	// ---------------------------------------------------------------------------
	// Tab state — driven by ?tab= query param, default "live"
	// ---------------------------------------------------------------------------
	let activeTab = $state<'live' | 'audit'>('live');

	$effect(() => {
		const tab = $page.url.searchParams.get('tab');
		activeTab = tab === 'audit' ? 'audit' : 'live';
	});

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------
	let entries = $state<LogEntry[]>([]);
	let captureLevel = $state('DEBUG');
	let validLevels = $state<string[]>(LOG_LEVELS);
	let loading = $state(true);
	let autoRefresh = $state(true);
	let intervalId = $state<number | null>(null);
	let tail = $state(500);
	let filterLevel = $state('ALL');
	let loggerFilter = $state('');
	let autoScroll = $state(true);
	let logContainer: HTMLElement | undefined = $state();

	// ---------------------------------------------------------------------------
	// Data loading
	// ---------------------------------------------------------------------------
	async function load() {
		try {
			const params: { tail: number; level?: string; logger?: string } = { tail };
			if (filterLevel !== 'ALL') params.level = filterLevel;
			if (loggerFilter.trim()) params.logger = loggerFilter.trim();
			const res = await api.admin.getLogs(params);
			entries = res.entries;
			captureLevel = res.capture_level;
			validLevels = res.valid_levels;
			if (autoScroll) {
				requestAnimationFrame(scrollToBottom);
			}
		} catch (e) {
			flash.error('Failed to load logs');
		} finally {
			loading = false;
		}
	}

	function scrollToBottom() {
		if (logContainer) {
			logContainer.scrollTop = logContainer.scrollHeight;
		}
	}

	// ---------------------------------------------------------------------------
	// Auto-refresh management
	// ---------------------------------------------------------------------------
	function startAutoRefresh() {
		stopAutoRefresh();
		intervalId = window.setInterval(load, 3000);
	}

	function stopAutoRefresh() {
		if (intervalId !== null) {
			window.clearInterval(intervalId);
			intervalId = null;
		}
	}

	function toggleAutoRefresh() {
		autoRefresh = !autoRefresh;
		if (autoRefresh) {
			startAutoRefresh();
		} else {
			stopAutoRefresh();
		}
	}

	// ---------------------------------------------------------------------------
	// Level changing
	// ---------------------------------------------------------------------------
	async function changeCaptureLevel(level: string) {
		try {
			const res = await api.admin.setLogLevel(level);
			captureLevel = res.level;
			flash.success(`Capture level set to ${res.level}`);
			await load();
		} catch (e) {
			flash.error('Failed to change log level');
		}
	}

	// ---------------------------------------------------------------------------
	// Copy all
	// ---------------------------------------------------------------------------
	function copyAll() {
		const text = entries
			.map((e) => `${e.timestamp} [${e.level.padEnd(8)}] ${e.logger} — ${e.message}`)
			.join('\n');
		navigator.clipboard.writeText(text).then(
			() => flash.success(`Copied ${entries.length} log entries`),
			() => flash.error('Failed to copy to clipboard')
		);
	}

	function clearView() {
		entries = [];
	}

	// ---------------------------------------------------------------------------
	// Lifecycle
	// ---------------------------------------------------------------------------
	onMount(() => {
		load();
		startAutoRefresh();
		return () => stopAutoRefresh();
	});

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------
	const LEVEL_COLORS: Record<string, string> = {
		DEBUG: 'text-zinc-500',
		INFO: 'text-sky-400',
		WARNING: 'text-amber-400',
		ERROR: 'text-red-400',
		CRITICAL: 'text-red-500 font-bold',
	};

	const LEVEL_BG: Record<string, string> = {
		DEBUG: '',
		INFO: '',
		WARNING: 'bg-amber-500/5',
		ERROR: 'bg-red-500/5',
		CRITICAL: 'bg-red-500/10',
	};

	function levelColor(level: string): string {
		return LEVEL_COLORS[level] || 'text-zinc-400';
	}

	function levelBg(level: string): string {
		return LEVEL_BG[level] || '';
	}

	function fmtTime(iso: string): string {
		try {
			const d = new Date(iso);
			return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
		} catch {
			return iso;
		}
	}
</script>

<svelte:head>
	<title>{activeTab === 'audit' ? 'Audit Log' : 'Live Logs'} · Synapse</title>
</svelte:head>

<!-- Tab Switcher -->
<div class="flex items-center gap-1 mb-4 bg-surface-100 border border-surface-300 rounded-xl p-1 w-fit">
	<button
		class="px-4 py-2 rounded-lg text-sm font-medium transition-all {activeTab === 'live' ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'text-zinc-400 hover:text-zinc-200 hover:bg-surface-200'}"
		onclick={() => { activeTab = 'live'; history.replaceState(null, '', '/admin/logs?tab=live'); }}
	>
		Live Logs
	</button>
	<button
		class="px-4 py-2 rounded-lg text-sm font-medium transition-all {activeTab === 'audit' ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'text-zinc-400 hover:text-zinc-200 hover:bg-surface-200'}"
		onclick={() => { activeTab = 'audit'; history.replaceState(null, '', '/admin/logs?tab=audit'); }}
	>
		Audit Log
	</button>
</div>

{#if activeTab === 'audit'}
	<AuditLogView />
{:else}
<div class="flex flex-col h-[calc(100vh-8rem)] gap-4">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-white">Live Logs</h1>
			<p class="text-sm text-zinc-500 mt-1">
				Stream of consciousness — API process ring buffer ({entries.length} entries)
			</p>
		</div>
	</div>

	<!-- Toolbar -->
	<div class="flex flex-wrap items-center gap-3 bg-surface-100 border border-surface-300 rounded-xl px-4 py-3">
		<!-- Capture Level (server-side, on the fly) -->
		<div class="flex items-center gap-2">
			<span class="text-xs text-zinc-500 font-medium uppercase tracking-wider">Capture</span>
			<select
				class="select-sm"
				value={captureLevel}
				onchange={(e) => changeCaptureLevel(e.currentTarget.value)}
			>
				{#each validLevels as lvl}
					<option value={lvl}>{lvl}</option>
				{/each}
			</select>
		</div>

		<div class="w-px h-6 bg-surface-300"></div>

		<!-- Display Filter (client-side) -->
		<div class="flex items-center gap-2">
			<span class="text-xs text-zinc-500 font-medium uppercase tracking-wider">Filter</span>
			<select class="select-sm" bind:value={filterLevel} onchange={load}>
				<option value="ALL">ALL</option>
				{#each validLevels as lvl}
					<option value={lvl}>{lvl}+</option>
				{/each}
			</select>
		</div>

		<div class="w-px h-6 bg-surface-300"></div>

		<!-- Logger prefix filter -->
		<div class="flex items-center gap-2">
			<span class="text-xs text-zinc-500 font-medium uppercase tracking-wider">Logger</span>
			<input
				type="text"
				class="input-sm w-44"
				placeholder="e.g. synapse.bot"
				bind:value={loggerFilter}
				onkeydown={(e) => { if (e.key === 'Enter') load(); }}
			/>
		</div>

		<div class="w-px h-6 bg-surface-300"></div>

		<!-- Tail size -->
		<div class="flex items-center gap-2">
			<span class="text-xs text-zinc-500 font-medium uppercase tracking-wider">Lines</span>
			<select class="select-sm" bind:value={tail} onchange={load}>
				<option value={100}>100</option>
				<option value={200}>200</option>
				<option value={500}>500</option>
				<option value={1000}>1000</option>
				<option value={2000}>2000</option>
			</select>
		</div>

		<!-- Spacer -->
		<div class="flex-1"></div>

		<!-- Action buttons -->
		<label class="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer select-none">
			<input type="checkbox" bind:checked={autoScroll} class="accent-brand-500" />
			Auto-scroll
		</label>

		<button
			class="btn-sm {autoRefresh ? 'btn-primary' : 'btn-secondary'}"
			onclick={toggleAutoRefresh}
			title={autoRefresh ? 'Pause auto-refresh (3s)' : 'Resume auto-refresh'}
		>
			{autoRefresh ? '⏸ Live' : '▶ Paused'}
		</button>

		<button class="btn-sm btn-secondary" onclick={load} title="Refresh now">
			Refresh
		</button>

		<button class="btn-sm btn-secondary" onclick={copyAll} title="Copy all logs to clipboard">
			Copy
		</button>

		<button class="btn-sm btn-secondary" onclick={clearView} title="Clear the view (does not clear buffer)">
			Clear
		</button>
	</div>

	<!-- Log output -->
	<div
		bind:this={logContainer}
		class="flex-1 min-h-0 overflow-y-auto bg-surface-0 border border-surface-300 rounded-xl font-mono text-xs leading-relaxed"
	>
		{#if loading && entries.length === 0}
			<div class="flex items-center justify-center h-full text-zinc-500">
				Loading logs…
			</div>
		{:else if entries.length === 0}
			<div class="flex items-center justify-center h-full text-zinc-500">
				No log entries{filterLevel !== 'ALL' ? ` at ${filterLevel}+ level` : ''}.
				{#if captureLevel !== 'DEBUG'}
					Try lowering the capture level.
				{/if}
			</div>
		{:else}
			<table class="w-full">
				<tbody>
					{#each entries as entry, i}
						<tr class="border-b border-surface-200/50 hover:bg-surface-100/50 {levelBg(entry.level)}">
							<td class="pl-3 pr-2 py-0.5 text-zinc-600 whitespace-nowrap select-none w-0">
								{fmtTime(entry.timestamp)}
							</td>
							<td class="px-2 py-0.5 whitespace-nowrap font-semibold w-0 {levelColor(entry.level)}">
								{entry.level.padEnd(8)}
							</td>
							<td class="px-2 py-0.5 text-zinc-500 whitespace-nowrap w-0 max-w-[200px] truncate" title={entry.logger}>
								{entry.logger}
							</td>
							<td class="px-2 py-0.5 text-zinc-300 whitespace-pre-wrap break-all">
								{entry.message}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
{/if}

<style lang="postcss">
	.select-sm {
		@apply bg-surface-0 border border-surface-300 text-zinc-300 rounded-lg px-2 py-1 text-xs;
		@apply focus:ring-1 focus:ring-brand-500 focus:border-brand-500 outline-none;
	}

	.input-sm {
		@apply bg-surface-0 border border-surface-300 text-zinc-300 rounded-lg px-2 py-1 text-xs;
		@apply focus:ring-1 focus:ring-brand-500 focus:border-brand-500 outline-none;
		@apply placeholder:text-zinc-600;
	}

	.btn-sm {
		@apply inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors;
	}


</style>
