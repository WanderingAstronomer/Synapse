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

	/** Human-friendly labels for snake_case settings keys */
	const FRIENDLY_LABELS: Record<string, string> = {
		// Economy
		base_xp_message:         'Base XP per Message',
		base_xp_reaction:        'Base XP per Reaction',
		base_xp_voice_tick:      'Base XP per Voice Minute',
		base_xp_thread_create:   'Base XP for Creating a Thread',
		xp_per_level_base:       'XP Needed for Level 2',
		xp_per_level_exponent:   'Level Curve Steepness',
		gold_per_level:          'Gold Earned per Level Up',
		star_to_gold_ratio:      'Stars-to-Gold Exchange Rate',
		// Anti-gaming
		anti_gaming_velocity_cap:       'Spam Throttle (max events/min)',
		anti_gaming_cooldown_seconds:   'Cooldown Between Rewards (sec)',
		anti_gaming_min_message_length: 'Min Message Length for XP',
		anti_gaming_duplicate_window:   'Duplicate Detection Window (sec)',
		// Dashboard
		dashboard_title:         'Dashboard Title',
		dashboard_subtitle:      'Dashboard Subtitle',
		dashboard_hero_emoji:    'Hero Banner Emoji',
		// Discord
		guild_id:                'Discord Server ID',
		announce_channel_id:     'Announcement Channel',
		bot_status_text:         'Bot Status Message',
		// Seasons
		season_duration_days:    'Season Length (days)',
		season_auto_roll:        'Auto-Roll Seasons',
	};

	/** Category display config */
	const CATEGORY_META: Record<string, { icon: string; label: string; description: string; danger?: boolean }> = {
		economy:      { icon: '💰', label: 'Economy',           description: 'XP rates, leveling curve, and gold rewards' },
		anti_gaming:  { icon: '🛡️', label: 'Anti-Gaming',       description: 'Spam protection and reward throttling' },
		dashboard:    { icon: '🎨', label: 'Dashboard',         description: 'Branding, titles, and display settings' },
		discord:      { icon: '🤖', label: 'Discord',           description: 'Bot configuration and server integration' },
		seasons:      { icon: '📅', label: 'Seasons',           description: 'Season duration and rollover behavior' },
		dangerous:    { icon: '⚠️', label: 'Danger Zone',       description: 'Settings that can significantly affect the game', danger: true },
	};

	function friendlyLabel(key: string): string {
		return FRIENDLY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
	}

	async function load() {
		try {
			const res = await api.admin.getSettings();
			settings = res.settings;
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

	/** Group settings by category */
	const grouped = $derived(() => {
		const groups: Record<string, AdminSetting[]> = {};
		for (const s of filtered) {
			const cat = s.category || 'other';
			if (!groups[cat]) groups[cat] = [];
			groups[cat].push(s);
		}
		return groups;
	});

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
		{#if saving}
			<span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
			Saving…
		{:else}
			💾 Save {changedCount} change{changedCount !== 1 ? 's' : ''}
		{/if}
	</button>
</div>

<!-- Category filter pills -->
<div class="flex flex-wrap gap-2 mb-6">
	<button
		class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
			{!filterCategory ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => (filterCategory = '')}
	>
		All ({settings.length})
	</button>
	{#each categories as cat}
		{@const meta = CATEGORY_META[cat]}
		{@const count = settings.filter((s) => s.category === cat).length}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
				{filterCategory === cat ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => (filterCategory = cat)}
		>
			{meta?.icon || '📦'} {meta?.label || capitalize(cat)} ({count})
		</button>
	{/each}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else}
	{@const groups = grouped()}
	{#each Object.entries(groups) as [cat, catSettings] (cat)}
		{@const meta = CATEGORY_META[cat]}
		<div class="settings-group mb-6 {meta?.danger ? 'danger-zone' : ''}">
			<div class="settings-group-header flex items-center gap-3">
				<span class="text-lg">{meta?.icon || '📦'}</span>
				<div>
					<h3 class="text-sm font-semibold text-zinc-200">{meta?.label || capitalize(cat)}</h3>
					{#if meta?.description}
						<p class="text-xs text-zinc-500">{meta.description}</p>
					{/if}
				</div>
				{#if meta?.danger}
					<span class="ml-auto badge bg-red-500/10 text-red-400 border border-red-500/20">⚠ Caution</span>
				{/if}
			</div>
			<div class="divide-y divide-surface-300/30">
				{#each catSettings as s (s.key)}
					<div class="flex flex-col sm:flex-row sm:items-center gap-3 px-5 py-4 hover:bg-surface-200/30 transition-colors
						{hasChanged(s.key) ? 'bg-brand-500/5 border-l-2 border-l-brand-500' : ''}">
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								<span class="text-sm font-medium text-zinc-200">{friendlyLabel(s.key)}</span>
								{#if hasChanged(s.key)}
									<span class="w-2 h-2 rounded-full bg-brand-400 animate-pulse"></span>
								{/if}
							</div>
							<div class="flex items-center gap-2 mt-0.5">
								<code class="text-[10px] font-mono text-zinc-600">{s.key}</code>
								{#if s.description}
									<span class="text-[10px] text-zinc-500">— {s.description}</span>
								{/if}
							</div>
						</div>
						<div class="w-full sm:w-64">
							<input
								class="input text-sm font-mono"
								bind:value={editedValues[s.key]}
							/>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/each}
{/if}
