<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type AuditLogEntry } from '$lib/api';
	import { flash } from '$lib/stores/flash';
	import { userNames, requestResolve, resolveUser } from '$lib/stores/names';
	import { fmtDateTime, capitalize } from '$lib/utils';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';

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
			// Resolve actor IDs to usernames
			const actorIds = [...new Set(entries.map((e) => e.actor_id))];
			if (actorIds.length > 0) requestResolve(actorIds);
		} catch (e) { flash.error('Failed to load audit log'); }
		finally { loading = false; }
	}

	onMount(load);

	const totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

	function nextPage() { if (page < totalPages) { page++; load(); } }
	function prevPage() { if (page > 1) { page--; load(); } }
	function toggle(id: number) { expandedId = expandedId === id ? null : id; }

	const ACTION_STYLES: Record<string, { badge: string; icon: string }> = {
		CREATE:        { badge: 'bg-green-500/10 text-green-400 border border-green-500/20', icon: '+' },
		UPDATE:        { badge: 'bg-blue-500/10 text-blue-400 border border-blue-500/20', icon: '~' },
		DELETE:        { badge: 'bg-red-500/10 text-red-400 border border-red-500/20', icon: '×' },
		SEASON_ROLL:   { badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20', icon: '↻' },
		MANUAL_AWARD:  { badge: 'bg-brand-500/10 text-brand-400 border border-brand-500/20', icon: '★' },
		MANUAL_REVOKE: { badge: 'bg-red-500/10 text-red-400 border border-red-500/20', icon: '−' },
	};

	function getActionStyle(action: string) {
		return ACTION_STYLES[action] || { badge: 'bg-surface-300 text-zinc-400', icon: '•' };
	}

	/** Compute visual diff between before and after snapshots */
	function computeDiff(before: Record<string, unknown> | null, after: Record<string, unknown> | null): { key: string; before: string | null; after: string | null; type: 'added' | 'removed' | 'changed' | 'same' }[] {
		const allKeys = new Set([
			...Object.keys(before || {}),
			...Object.keys(after || {}),
		]);
		const diffs: { key: string; before: string | null; after: string | null; type: 'added' | 'removed' | 'changed' | 'same' }[] = [];
		for (const key of allKeys) {
			const bVal = before?.[key] !== undefined ? JSON.stringify(before[key]) : null;
			const aVal = after?.[key] !== undefined ? JSON.stringify(after[key]) : null;
			if (bVal === null && aVal !== null) {
				diffs.push({ key, before: null, after: aVal, type: 'added' });
			} else if (bVal !== null && aVal === null) {
				diffs.push({ key, before: bVal, after: null, type: 'removed' });
			} else if (bVal !== aVal) {
				diffs.push({ key, before: bVal, after: aVal, type: 'changed' });
			} else {
				diffs.push({ key, before: bVal, after: aVal, type: 'same' });
			}
		}
		// Sort: changed first, then added, then removed, then same
		const order = { changed: 0, added: 1, removed: 2, same: 3 };
		return diffs.sort((a, b) => order[a.type] - order[b.type]);
	}
</script>

<svelte:head><title>Admin: Audit Log — Synapse</title></svelte:head>

<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">📋 Audit Log</h1>
	<p class="text-sm text-zinc-500 mt-1">Every admin action, timestamped and snapshotted.</p>
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading audit log..." />
	</div>
{:else if entries.length === 0}
	<div class="card text-center py-12">
		<div class="w-16 h-16 rounded-2xl bg-surface-200 border border-surface-300 flex items-center justify-center mx-auto mb-4">
			<span class="text-3xl">📋</span>
		</div>
		<p class="text-zinc-300 font-medium">No audit entries yet</p>
		<p class="text-xs text-zinc-500 mt-1">Admin actions will appear here as they happen.</p>
	</div>
{:else}
	<div class="space-y-2">
		{#each entries as entry (entry.id)}
			{@const style = getActionStyle(entry.action_type)}
			<div class="card p-0 overflow-hidden">
				<button
					class="w-full flex items-center gap-4 px-4 py-3 hover:bg-surface-200/50 transition-all text-left"
					onclick={() => toggle(entry.id)}
				>
					<!-- Action icon -->
					<div class="w-8 h-8 rounded-lg {style.badge} flex items-center justify-center text-sm font-bold flex-shrink-0">
						{style.icon}
					</div>

					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2">
							<span class="text-sm font-medium text-zinc-200">{entry.action_type.replace(/_/g, ' ')}</span>
							<span class="text-xs text-zinc-500">on</span>
							<span class="text-xs font-mono text-zinc-400">{entry.target_table}</span>
							{#if entry.target_id}
								<span class="text-xs font-mono text-brand-400">#{entry.target_id}</span>
							{/if}
						</div>
						{#if entry.reason}
							<p class="text-xs text-zinc-500 mt-0.5 truncate">"{entry.reason}"</p>
						{/if}
					</div>

					<div class="flex items-center gap-3 flex-shrink-0">
						<span class="text-xs text-zinc-500">{fmtDateTime(entry.timestamp)}</span>
						<span class="text-zinc-500 text-xs transition-transform {expandedId === entry.id ? 'rotate-180' : ''}" style="transition: transform 0.2s ease;">▼</span>
					</div>
				</button>

				{#if expandedId === entry.id}
					<div class="px-4 pb-4 border-t border-surface-300 animate-fade-in">
						<!-- Visual diff table -->
						{#if entry.before_snapshot || entry.after_snapshot}
							{@const diffs = computeDiff(entry.before_snapshot, entry.after_snapshot)}
							{@const changedDiffs = diffs.filter(d => d.type !== 'same')}
							{#if changedDiffs.length > 0}
								<div class="mt-3 rounded-lg border border-surface-300 overflow-hidden">
									<div class="px-3 py-2 bg-surface-200/50 border-b border-surface-300">
										<span class="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Changes</span>
									</div>
									<div class="divide-y divide-surface-300/30">
										{#each changedDiffs as diff}
											<div class="flex items-start gap-3 px-3 py-2 text-xs">
												<span class="text-zinc-500 font-mono w-40 flex-shrink-0 pt-0.5">{diff.key}</span>
												<div class="flex-1 min-w-0">
													{#if diff.type === 'changed'}
														<div class="flex flex-col gap-1">
															<span class="diff-removed font-mono break-all">{diff.before}</span>
															<span class="diff-added font-mono break-all">{diff.after}</span>
														</div>
													{:else if diff.type === 'added'}
														<span class="diff-added font-mono break-all">+ {diff.after}</span>
													{:else if diff.type === 'removed'}
														<span class="diff-removed font-mono break-all">− {diff.before}</span>
													{/if}
												</div>
											</div>
										{/each}
									</div>
								</div>
							{:else}
								<p class="text-xs text-zinc-500 mt-3 italic">No field changes detected.</p>
							{/if}

							<!-- Unchanged fields (collapsed) -->
							{@const sameDiffs = diffs.filter(d => d.type === 'same')}
							{#if sameDiffs.length > 0}
								<details class="mt-2">
									<summary class="text-[10px] text-zinc-600 cursor-pointer hover:text-zinc-400 transition-colors">
										{sameDiffs.length} unchanged field{sameDiffs.length !== 1 ? 's' : ''}
									</summary>
									<div class="mt-1 rounded-lg bg-surface-200/30 p-2">
										{#each sameDiffs as diff}
											<div class="flex items-center gap-2 text-[10px] text-zinc-600 font-mono py-0.5">
												<span class="w-40">{diff.key}</span>
												<span class="truncate">{diff.before}</span>
											</div>
										{/each}
									</div>
								</details>
							{/if}
						{:else}
							<p class="text-xs text-zinc-500 mt-3 italic">No snapshot data available.</p>
						{/if}

						<div class="flex items-center gap-4 mt-3 pt-3 border-t border-surface-300/30">
							<p class="text-xs text-zinc-500">
								Actor: <span class="font-mono text-brand-400">{resolveUser(entry.actor_id, $userNames)}</span>
							</p>
							<p class="text-xs text-zinc-500">
								Entry: <span class="font-mono text-zinc-400">#{entry.id}</span>
							</p>
						</div>
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
