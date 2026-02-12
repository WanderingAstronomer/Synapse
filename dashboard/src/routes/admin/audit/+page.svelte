<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type AuditLogEntry } from '$lib/api';
	import { flash } from '$lib/stores/flash';
	import { fmtDateTime, capitalize } from '$lib/utils';

	let entries = $state<AuditLogEntry[]>([]);
	let total = $state(0);
	let page = $state(1);
	let pageSize = $state(25);
	let loading = $state(true);
	let expandedId = $state<number | null>(null);

	async function load() {
		loading = true;
		try {
			const res = await api.admin.getAuditLog(page, pageSize);
			entries = res.entries;
			total = res.total;
		} catch (e) { flash.error('Failed to load audit log'); }
		finally { loading = false; }
	}

	onMount(load);

	const totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

	function nextPage() { if (page < totalPages) { page++; load(); } }
	function prevPage() { if (page > 1) { page--; load(); } }
	function toggle(id: number) { expandedId = expandedId === id ? null : id; }

	const ACTION_STYLES: Record<string, string> = {
		CREATE: 'bg-green-500/10 text-green-400',
		UPDATE: 'bg-blue-500/10 text-blue-400',
		DELETE: 'bg-red-500/10 text-red-400',
		SEASON_ROLL: 'bg-amber-500/10 text-amber-400',
		MANUAL_AWARD: 'bg-brand-500/10 text-brand-400',
		MANUAL_REVOKE: 'bg-red-500/10 text-red-400',
	};
</script>

<svelte:head><title>Admin: Audit Log — Synapse</title></svelte:head>

<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">📋 Audit Log</h1>
	<p class="text-sm text-zinc-500 mt-1">Every admin action, timestamped and snapshotted.</p>
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if entries.length === 0}
	<div class="card text-center py-12">
		<span class="text-4xl">📋</span>
		<p class="text-zinc-400 mt-2">No audit entries yet.</p>
	</div>
{:else}
	<div class="space-y-2">
		{#each entries as entry (entry.id)}
			<div class="card p-0 overflow-hidden">
				<button
					class="w-full flex items-center gap-4 px-4 py-3 hover:bg-surface-200/50 transition-colors text-left"
					onclick={() => toggle(entry.id)}
				>
					<span class="badge text-[10px] {ACTION_STYLES[entry.action_type] || 'bg-surface-300 text-zinc-400'}">
						{entry.action_type}
					</span>
					<span class="text-sm text-zinc-300 flex-1">
						<span class="text-zinc-500">{entry.target_table}</span>
						{#if entry.target_id}
							<span class="font-mono text-xs text-brand-400 ml-1">#{entry.target_id}</span>
						{/if}
					</span>
					<span class="text-xs text-zinc-500">{fmtDateTime(entry.timestamp)}</span>
					<span class="text-zinc-500 text-xs">{expandedId === entry.id ? '▲' : '▼'}</span>
				</button>

				{#if expandedId === entry.id}
					<div class="px-4 pb-4 border-t border-surface-300 animate-fade-in">
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
							<div>
								<p class="text-[10px] font-semibold text-zinc-500 uppercase mb-1">Before</p>
								<pre class="text-xs text-zinc-400 bg-surface-200 rounded-lg p-3 overflow-x-auto max-h-48">{entry.before_snapshot ? JSON.stringify(entry.before_snapshot, null, 2) : '—'}</pre>
							</div>
							<div>
								<p class="text-[10px] font-semibold text-zinc-500 uppercase mb-1">After</p>
								<pre class="text-xs text-zinc-400 bg-surface-200 rounded-lg p-3 overflow-x-auto max-h-48">{entry.after_snapshot ? JSON.stringify(entry.after_snapshot, null, 2) : '—'}</pre>
							</div>
						</div>
						{#if entry.reason}
							<p class="text-xs text-zinc-500 mt-2"><strong>Reason:</strong> {entry.reason}</p>
						{/if}
						<p class="text-xs text-zinc-500 mt-1">Actor: <span class="font-mono text-brand-400">{entry.actor_id}</span></p>
					</div>
				{/if}
			</div>
		{/each}
	</div>

	<!-- Pagination -->
	<div class="flex items-center justify-between mt-4">
		<p class="text-xs text-zinc-500">
			Page {page} of {totalPages} ({total} entries)
		</p>
		<div class="flex gap-2">
			<button class="btn-secondary text-xs" onclick={prevPage} disabled={page <= 1}>← Prev</button>
			<button class="btn-secondary text-xs" onclick={nextPage} disabled={page >= totalPages}>Next →</button>
		</div>
	</div>
{/if}
