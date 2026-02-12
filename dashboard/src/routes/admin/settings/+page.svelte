<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type AdminSetting } from '$lib/api';
	import { flash } from '$lib/stores/flash';
	import { capitalize } from '$lib/utils';

	let settings = $state<AdminSetting[]>([]);
	let loading = $state(true);
	let editedValues = $state<Record<string, string>>({});
	let saving = $state(false);
	let filterCategory = $state('');

	async function load() {
		try {
			const res = await api.admin.getSettings();
			settings = res.settings;
			// Initialize edit values
			editedValues = {};
			for (const s of settings) {
				editedValues[s.key] = typeof s.value === 'string' ? s.value : JSON.stringify(s.value);
			}
		} catch (e) { flash.error('Failed to load settings'); }
		finally { loading = false; }
	}

	onMount(load);

	const categories = $derived([...new Set(settings.map((s) => s.category))].sort());

	const filtered = $derived(
		filterCategory ? settings.filter((s) => s.category === filterCategory) : settings
	);

	function hasChanged(key: string): boolean {
		const orig = settings.find((s) => s.key === key);
		if (!orig) return false;
		const origStr = typeof orig.value === 'string' ? orig.value : JSON.stringify(orig.value);
		return editedValues[key] !== origStr;
	}

	const changedCount = $derived(settings.filter((s) => hasChanged(s.key)).length);

	async function saveAll() {
		const changed = settings
			.filter((s) => hasChanged(s.key))
			.map((s) => {
				let val: unknown;
				try { val = JSON.parse(editedValues[s.key]); } catch { val = editedValues[s.key]; }
				return { key: s.key, value: val, category: s.category };
			});

		if (changed.length === 0) { flash.info('No changes to save'); return; }
		saving = true;
		try {
			await api.admin.updateSettings(changed);
			flash.success(`${changed.length} setting(s) updated`);
			await load();
		} catch (e: any) { flash.error(e.message); }
		finally { saving = false; }
	}
</script>

<svelte:head><title>Admin: Settings — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">⚙️ Settings</h1>
		<p class="text-sm text-zinc-500 mt-1">Tune gameplay parameters and dashboard branding.</p>
	</div>
	<button class="btn-primary" onclick={saveAll} disabled={saving || changedCount === 0}>
		{saving ? 'Saving…' : `Save ${changedCount} change${changedCount !== 1 ? 's' : ''}`}
	</button>
</div>

<!-- Category filter -->
<div class="flex flex-wrap gap-2 mb-6">
	<button
		class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
			{!filterCategory ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => (filterCategory = '')}
	>
		All ({settings.length})
	</button>
	{#each categories as cat}
		{@const count = settings.filter((s) => s.category === cat).length}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{filterCategory === cat ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => (filterCategory = cat)}
		>
			{capitalize(cat)} ({count})
		</button>
	{/each}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else}
	<div class="space-y-3">
		{#each filtered as s (s.key)}
			<div class="card {hasChanged(s.key) ? 'ring-2 ring-brand-500/40' : ''}">
				<div class="flex flex-col sm:flex-row sm:items-center gap-3">
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2">
							<code class="text-xs font-mono text-brand-400">{s.key}</code>
							<span class="badge bg-surface-300 text-zinc-500">{s.category}</span>
						</div>
						{#if s.description}
							<p class="text-xs text-zinc-500 mt-0.5">{s.description}</p>
						{/if}
					</div>
					<div class="w-full sm:w-64">
						<input
							class="input text-sm font-mono"
							bind:value={editedValues[s.key]}
						/>
					</div>
				</div>
			</div>
		{/each}
	</div>
{/if}
