<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type AdminAchievement,
		type AchievementCategoryItem,
		type AchievementRarityItem,
		type AchievementSeriesItem,
		type TriggerTypeInfo,
		type MediaFileItem,
	} from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { capitalize } from '$lib/utils';
	import { currency } from '$lib/stores/currency.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';

	// --- Data ---
	let achievements = $state<AdminAchievement[]>([]);
	let categories = $state<AchievementCategoryItem[]>([]);
	let rarities = $state<AchievementRarityItem[]>([]);
	let series = $state<AchievementSeriesItem[]>([]);
	let triggerTypes = $state<TriggerTypeInfo[]>([]);
	let loading = $state(true);

	// --- Form state ---
	let showForm = $state(false);
	let editId = $state<number | null>(null);

	let f = $state({
		name: '',
		description: '',
		category_id: null as number | null,
		rarity_id: null as number | null,
		trigger_type: 'manual',
		trigger_config: {} as Record<string, unknown>,
		series_id: null as number | null,
		series_order: null as number | null,
		xp_reward: 0,
		gold_reward: 0,
		badge_image: '',
		is_hidden: false,
		max_earners: null as number | null,
	});

	// --- Inline taxonomy management (inside form) ---
	let managingSection = $state<'categories' | 'rarities' | 'series' | null>(null);
	let catForm = $state({ name: '', icon: '', sort_order: 0, editId: null as number | null });
	let rarForm = $state({ name: '', color: '#9e9e9e', emoji: '', sort_order: 0, editId: null as number | null });
	let serForm = $state({ name: '', description: '', editId: null as number | null });

	// --- Media picker ---
	let showMediaPicker = $state(false);
	let mediaFiles = $state<MediaFileItem[]>([]);
	let mediaLoaded = $state(false);

	// --- Trigger config fields (dynamic) ---
	let selectedTrigger = $derived(triggerTypes.find((t) => t.value === f.trigger_type));
	let configFields = $derived(
		selectedTrigger?.config_schema
			? Object.entries(selectedTrigger.config_schema as Record<string, { type: string; label?: string; description?: string; options?: string[] }>)
			: []
	);

	// --- Helpers ---
	function categoryName(id: number | null): string {
		if (!id) return '—';
		return categories.find((c) => c.id === id)?.name ?? '—';
	}
	function rarityName(id: number | null): string {
		if (!id) return '—';
		return rarities.find((r) => r.id === id)?.name ?? '—';
	}
	function rarityColor(id: number | null): string {
		if (!id) return '#9e9e9e';
		return rarities.find((r) => r.id === id)?.color ?? '#9e9e9e';
	}
	function seriesName(id: number | null): string {
		if (!id) return '—';
		return series.find((s) => s.id === id)?.name ?? '—';
	}
	function triggerLabel(type: string): string {
		return triggerTypes.find((t) => t.value === type)?.label ?? type;
	}

	// --- Data loading ---
	async function loadAll() {
		try {
			const [achRes, catRes, rarRes, serRes, ttRes] = await Promise.all([
				api.admin.getAchievements(),
				api.admin.getAchievementCategories(),
				api.admin.getAchievementRarities(),
				api.admin.getAchievementSeries(),
				api.admin.getTriggerTypes(),
			]);
			achievements = achRes.achievements;
			categories = catRes.categories;
			rarities = rarRes.rarities;
			series = serRes.series;
			triggerTypes = ttRes.trigger_types;
		} catch (e) {
			flash.error('Failed to load achievement data');
		} finally {
			loading = false;
		}
	}

	onMount(loadAll);

	// --- Achievement CRUD ---
	function resetForm() {
		f = {
			name: '', description: '', category_id: null, rarity_id: null,
			trigger_type: 'manual', trigger_config: {}, series_id: null,
			series_order: null, xp_reward: 0, gold_reward: 0, badge_image: '',
			is_hidden: false, max_earners: null,
		};
		showForm = false;
		editId = null;
	}

	function startEdit(a: AdminAchievement) {
		editId = a.id;
		f = {
			name: a.name,
			description: a.description || '',
			category_id: a.category_id,
			rarity_id: a.rarity_id,
			trigger_type: a.trigger_type,
			trigger_config: (a.trigger_config ?? {}) as Record<string, unknown>,
			series_id: a.series_id,
			series_order: a.series_order,
			xp_reward: a.xp_reward,
			gold_reward: a.gold_reward,
			badge_image: a.badge_image || '',
			is_hidden: a.is_hidden,
			max_earners: a.max_earners,
		};
		showForm = true;
	}

	async function handleSubmit() {
		if (!f.name.trim()) { flash.warning('Name is required'); return; }
		const payload = {
			name: f.name.trim(),
			description: f.description.trim() || undefined,
			category_id: f.category_id,
			rarity_id: f.rarity_id,
			trigger_type: f.trigger_type,
			trigger_config: f.trigger_config,
			series_id: f.series_id,
			series_order: f.series_order,
			xp_reward: f.xp_reward,
			gold_reward: f.gold_reward,
			badge_image: f.badge_image || undefined,
			is_hidden: f.is_hidden,
			max_earners: f.max_earners,
		};
		try {
			if (editId) {
				await api.admin.updateAchievement(editId, payload);
				flash.success('Achievement updated');
			} else {
				await api.admin.createAchievement(payload);
				flash.success(`Achievement "${f.name}" created`);
			}
			resetForm();
			await loadAll();
		} catch (e: any) { flash.error(e.message || 'Save failed'); }
	}

	async function toggleActive(a: AdminAchievement) {
		try {
			await api.admin.updateAchievement(a.id, { active: !a.active });
			flash.success(a.active ? 'Deactivated' : 'Activated');
			await loadAll();
		} catch (e: any) { flash.error(e.message); }
	}

	async function deleteAchievement(a: AdminAchievement) {
		if (!confirm(`Delete "${a.name}"? This cannot be undone.`)) return;
		try {
			await api.admin.deleteAchievement(a.id);
			flash.success(`Deleted "${a.name}"`);
			await loadAll();
		} catch (e: any) { flash.error(e.message); }
	}

	// --- Badge upload ---
	async function handleBadgeUpload(e: Event) {
		const input = e.target as HTMLInputElement;
		if (!input.files?.length) return;
		try {
			const res = await api.admin.uploadBadge(input.files[0]);
			f.badge_image = res.url;
			flash.success('Badge uploaded');
		} catch (err: any) { flash.error(err.message || 'Upload failed'); }
	}

	// --- Media picker ---
	async function openMediaPicker() {
		showMediaPicker = true;
		if (!mediaLoaded) {
			try {
				const res = await api.admin.getMedia();
				mediaFiles = res.files;
				mediaLoaded = true;
			} catch (e) { flash.error('Failed to load media library'); }
		}
	}

	function selectMedia(url: string) {
		f.badge_image = url;
		showMediaPicker = false;
	}

	// --- Category CRUD ---
	function resetCatForm() { catForm = { name: '', icon: '', sort_order: 0, editId: null }; }
	async function handleCatSubmit() {
		if (!catForm.name.trim()) return;
		try {
			if (catForm.editId) {
				await api.admin.updateAchievementCategory(catForm.editId, {
					name: catForm.name.trim(), icon: catForm.icon || undefined, sort_order: catForm.sort_order,
				});
			} else {
				await api.admin.createAchievementCategory({
					name: catForm.name.trim(), icon: catForm.icon || undefined, sort_order: catForm.sort_order,
				});
			}
			resetCatForm();
			const res = await api.admin.getAchievementCategories();
			categories = res.categories;
		} catch (e: any) { flash.error(e.message); }
	}
	async function deleteCat(id: number) {
		if (!confirm('Delete this category?')) return;
		try { await api.admin.deleteAchievementCategory(id); const res = await api.admin.getAchievementCategories(); categories = res.categories; }
		catch (e: any) { flash.error(e.message); }
	}

	// --- Rarity CRUD ---
	function resetRarForm() { rarForm = { name: '', color: '#9e9e9e', emoji: '', sort_order: 0, editId: null }; }
	async function handleRarSubmit() {
		if (!rarForm.name.trim()) return;
		try {
			if (rarForm.editId) {
				await api.admin.updateAchievementRarity(rarForm.editId, {
					name: rarForm.name.trim(), color: rarForm.color, emoji: rarForm.emoji || undefined, sort_order: rarForm.sort_order,
				});
			} else {
				await api.admin.createAchievementRarity({
					name: rarForm.name.trim(), color: rarForm.color, emoji: rarForm.emoji || undefined, sort_order: rarForm.sort_order,
				});
			}
			resetRarForm();
			const res = await api.admin.getAchievementRarities();
			rarities = res.rarities;
		} catch (e: any) { flash.error(e.message); }
	}
	async function deleteRar(id: number) {
		if (!confirm('Delete this rarity?')) return;
		try { await api.admin.deleteAchievementRarity(id); const res = await api.admin.getAchievementRarities(); rarities = res.rarities; }
		catch (e: any) { flash.error(e.message); }
	}

	// --- Series CRUD ---
	function resetSerForm() { serForm = { name: '', description: '', editId: null }; }
	async function handleSerSubmit() {
		if (!serForm.name.trim()) return;
		try {
			if (serForm.editId) {
				await api.admin.updateAchievementSeries(serForm.editId, {
					name: serForm.name.trim(), description: serForm.description.trim() || undefined,
				});
			} else {
				await api.admin.createAchievementSeries({
					name: serForm.name.trim(), description: serForm.description.trim() || undefined,
				});
			}
			resetSerForm();
			const res = await api.admin.getAchievementSeries();
			series = res.series;
		} catch (e: any) { flash.error(e.message); }
	}
	async function deleteSer(id: number) {
		try { await api.admin.deleteAchievementSeries(id); const res = await api.admin.getAchievementSeries(); series = res.series; }
		catch (e: any) { flash.error(e.message); }
	}
</script>

<svelte:head><title>Admin: Achievements — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">Achievements</h1>
		<p class="text-sm text-zinc-500 mt-1">Define badges, trigger rules, and progression series.</p>
	</div>
	{#if !showForm}
		<button class="btn-primary" onclick={() => { resetForm(); showForm = true; }}>+ New Achievement</button>
	{/if}
</div>

<!-- ==================== ACHIEVEMENT FORM ==================== -->
{#if showForm}
	<div class="card mb-6 animate-slide-up">
		<h3 class="text-sm font-semibold text-zinc-300 mb-4">{editId ? 'Edit Achievement' : 'New Achievement'}</h3>

		<!-- Row 1: Name + Description -->
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
			<div>
				<label class="label" for="ach-name">Name *</label>
				<input id="ach-name" class="input" bind:value={f.name} placeholder="First Steps" />
			</div>
			<div>
				<label class="label" for="ach-desc">Description</label>
				<input id="ach-desc" class="input" bind:value={f.description} placeholder="Send your first message" />
			</div>
		</div>

		<!-- Row 2: Category + Rarity (with inline manage) -->
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
			<!-- Category -->
			<div>
				<div class="flex items-center justify-between mb-1">
					<label class="label !mb-0" for="ach-cat">Category</label>
					<button class="text-[11px] text-brand-400 hover:text-brand-300"
						onclick={() => managingSection = managingSection === 'categories' ? null : 'categories'}>
						{managingSection === 'categories' ? 'Done' : 'Manage'}
					</button>
				</div>
				<select id="ach-cat" class="input" bind:value={f.category_id}>
					<option value={null}>— None —</option>
					{#each categories as c}<option value={c.id}>{c.icon ? c.icon + ' ' : ''}{c.name}</option>{/each}
				</select>
				{#if managingSection === 'categories'}
					<div class="mt-2 p-3 rounded-lg bg-surface-200/50 border border-surface-300 space-y-2">
						{#each categories as c (c.id)}
							<div class="flex items-center justify-between text-sm">
								<span class="text-zinc-300">{c.icon ? c.icon + ' ' : ''}{c.name}</span>
								<div class="flex gap-1">
									<button class="text-[11px] text-zinc-400 hover:text-white"
										onclick={() => { catForm = { name: c.name, icon: c.icon ?? '', sort_order: c.sort_order, editId: c.id }; }}>
										Edit
									</button>
									<button class="text-[11px] text-red-400 hover:text-red-300" onclick={() => deleteCat(c.id)}>Delete</button>
								</div>
							</div>
						{/each}
						<div class="flex gap-2 pt-1">
							<div class="flex-1">
							<label class="text-[10px] text-zinc-500 block mb-0.5">
								Name
								<input class="input !text-xs !py-1 mt-0.5 block w-full" bind:value={catForm.name} placeholder="Social" />
							</label>
						</div>
						<div class="w-14">
							<label class="text-[10px] text-zinc-500 block mb-0.5">
								Icon
								<input class="input !text-xs !py-1 mt-0.5 block w-full" bind:value={catForm.icon} placeholder="🏆" />
							</label>
						</div>
						<div class="w-14">
							<label class="text-[10px] text-zinc-500 block mb-0.5">
								Order
								<input class="input !text-xs !py-1 mt-0.5 block w-full" type="number" bind:value={catForm.sort_order} placeholder="0" />
							</label>
							</div>
							<button class="btn-primary !text-xs !px-2 !py-1" onclick={handleCatSubmit}>
								{catForm.editId ? 'Save' : 'Add'}
							</button>
							{#if catForm.editId}
								<button class="btn-secondary !text-xs !px-2 !py-1" onclick={resetCatForm}>✕</button>
							{/if}
						</div>
					</div>
				{/if}
			</div>

			<!-- Rarity -->
			<div>
				<div class="flex items-center justify-between mb-1">
					<label class="label !mb-0" for="ach-rar">Rarity</label>
					<button class="text-[11px] text-brand-400 hover:text-brand-300"
						onclick={() => managingSection = managingSection === 'rarities' ? null : 'rarities'}>
						{managingSection === 'rarities' ? 'Done' : 'Manage'}
					</button>
				</div>
				<select id="ach-rar" class="input" bind:value={f.rarity_id}>
					<option value={null}>— None —</option>
					{#each rarities as r}
						<option value={r.id}>{r.name}</option>
					{/each}
				</select>
				{#if managingSection === 'rarities'}
					<div class="mt-2 p-3 rounded-lg bg-surface-200/50 border border-surface-300 space-y-2">
						{#each rarities as r (r.id)}
							<div class="flex items-center justify-between text-sm">
								<div class="flex items-center gap-2">
									<span class="w-3 h-3 rounded-full inline-block" style="background-color: {r.color}"></span>
									<span class="text-zinc-300">{r.name}</span>
								</div>
								<div class="flex gap-1">
									<button class="text-[11px] text-zinc-400 hover:text-white"
										onclick={() => { rarForm = { name: r.name, color: r.color, emoji: r.emoji ?? '', sort_order: r.sort_order, editId: r.id }; }}>
										Edit
									</button>
									<button class="text-[11px] text-red-400 hover:text-red-300" onclick={() => deleteRar(r.id)}>Delete</button>
								</div>
							</div>
						{/each}
						<div class="flex gap-2 pt-1">
							<div class="flex-1">
								<label class="text-[10px] text-zinc-500 block mb-0.5">
									Name
									<input class="input !text-xs !py-1 mt-0.5 block w-full" bind:value={rarForm.name} placeholder="Legendary" />
								</label>
							</div>
							<div class="w-12">
								<label class="text-[10px] text-zinc-500 block mb-0.5">
									Color
									<input class="input !py-1 !px-1 w-full mt-0.5 block" type="color" bind:value={rarForm.color} />
								</label>
							</div>
							<div class="w-14">
								<label class="text-[10px] text-zinc-500 block mb-0.5">
									Emoji
									<input class="input !text-xs !py-1 mt-0.5 block w-full" bind:value={rarForm.emoji} placeholder="✨" />
								</label>
							</div>
							<div class="w-14">
								<label class="text-[10px] text-zinc-500 block mb-0.5">
									Order
									<input class="input !text-xs !py-1 mt-0.5 block w-full" type="number" bind:value={rarForm.sort_order} placeholder="0" />
								</label>
							</div>
							<button class="btn-primary !text-xs !px-2 !py-1" onclick={handleRarSubmit}>
								{rarForm.editId ? 'Save' : 'Add'}
							</button>
							{#if rarForm.editId}
								<button class="btn-secondary !text-xs !px-2 !py-1" onclick={resetRarForm}>✕</button>
							{/if}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Row 3: Trigger Type + Config -->
		<div class="mb-4">
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
				<div>
					<label class="label" for="ach-trigger">Trigger Type</label>
					<select id="ach-trigger" class="input" bind:value={f.trigger_type}
						onchange={() => { f.trigger_config = {}; }}>
						{#each triggerTypes as tt}
							<option value={tt.value}>{tt.label}</option>
						{/each}
					</select>
					{#if selectedTrigger}
						<p class="text-xs text-zinc-500 mt-1">{selectedTrigger.description}</p>
					{/if}
				</div>

				<!-- Dynamic trigger config fields -->
				{#each configFields as [key, schema]}
					<div>
						<label class="label" for="tc-{key}">{schema.label || capitalize(key.replace(/_/g, ' '))}</label>
						{#if schema.type === 'select' && schema.options}
							<select id="tc-{key}" class="input"
								value={f.trigger_config[key] ?? ''}
								onchange={(e) => { f.trigger_config[key] = (e.target as HTMLSelectElement).value; }}>
								<option value="">— Select —</option>
								{#each schema.options as opt}
									<option value={opt}>{capitalize(opt.toLowerCase().replace(/_/g, ' '))}</option>
								{/each}
							</select>
						{:else if schema.type === 'integer' || schema.type === 'number'}
							<input id="tc-{key}" class="input" type="number"
								value={f.trigger_config[key] ?? ''}
								oninput={(e) => { f.trigger_config[key] = Number((e.target as HTMLInputElement).value); }}
							/>
						{:else}
							<input id="tc-{key}" class="input"
								value={f.trigger_config[key] ?? ''}
								oninput={(e) => { f.trigger_config[key] = (e.target as HTMLInputElement).value; }}
							/>
						{/if}
						{#if schema.description}
							<p class="text-xs text-zinc-500 mt-0.5">{schema.description}</p>
						{/if}
					</div>
				{/each}
			</div>
		</div>

		<!-- Row 4: Series + Rewards -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
			<!-- Series -->
			<div>
				<div class="flex items-center justify-between mb-1">
					<label class="label !mb-0" for="ach-series">Progression Series</label>
					<button class="text-[11px] text-brand-400 hover:text-brand-300"
						onclick={() => managingSection = managingSection === 'series' ? null : 'series'}>
						{managingSection === 'series' ? 'Done' : 'Manage'}
					</button>
				</div>
				<select id="ach-series" class="input" bind:value={f.series_id}>
					<option value={null}>— None —</option>
					{#each series as s}<option value={s.id}>{s.name}</option>{/each}
				</select>
				{#if managingSection === 'series'}
					<div class="mt-2 p-3 rounded-lg bg-surface-200/50 border border-surface-300 space-y-2">
						{#each series as s (s.id)}
							<div class="flex items-center justify-between text-sm">
								<div>
									<span class="text-zinc-300">{s.name}</span>
									{#if s.description}<span class="text-xs text-zinc-500 ml-1">— {s.description}</span>{/if}
								</div>
								<div class="flex gap-1">
									<button class="text-[11px] text-zinc-400 hover:text-white"
										onclick={() => { serForm = { name: s.name, description: s.description ?? '', editId: s.id }; }}>
										Edit
									</button>
									<button class="text-[11px] text-red-400 hover:text-red-300" onclick={() => deleteSer(s.id)}>Delete</button>
								</div>
							</div>
						{/each}
						<div class="flex gap-2 pt-1">
							<input class="input flex-1 !text-xs !py-1" bind:value={serForm.name} placeholder="Series name" />
							<input class="input flex-1 !text-xs !py-1" bind:value={serForm.description} placeholder="Description" />
							<button class="btn-primary !text-xs !px-2 !py-1" onclick={handleSerSubmit}>
								{serForm.editId ? 'Save' : 'Add'}
							</button>
							{#if serForm.editId}
								<button class="btn-secondary !text-xs !px-2 !py-1" onclick={resetSerForm}>✕</button>
							{/if}
						</div>
					</div>
				{/if}
			</div>

			{#if f.series_id}
				<div>
					<label class="label" for="ach-sorder">Tier (order in series)</label>
					<input id="ach-sorder" class="input" type="number" bind:value={f.series_order} min="1" />
				</div>
			{/if}

			<!-- Rewards -->
			<div>
				<label class="label" for="ach-xp">{currency.primary} Reward</label>
				<input id="ach-xp" class="input" type="number" bind:value={f.xp_reward} />
			</div>
			<div>
				<label class="label" for="ach-gold">{currency.secondary} Reward</label>
				<input id="ach-gold" class="input" type="number" bind:value={f.gold_reward} />
			</div>
		</div>

		<!-- Row 5: Badge + Options -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
			<div>
				<label class="label" for="badge-image-picker">Badge Image</label>
				<div class="flex gap-2 items-center">
					{#if f.badge_image}
						<img src={f.badge_image} alt="badge" class="h-10 w-10 rounded object-cover border border-surface-300" />
					{/if}
					<button id="badge-image-picker" class="btn-secondary text-xs" type="button" onclick={openMediaPicker}>
						{f.badge_image ? 'Change' : 'Select from Media'}
					</button>
					{#if f.badge_image}
						<button class="text-xs text-red-400 hover:text-red-300" type="button"
							onclick={() => { f.badge_image = ''; }}>Remove</button>
					{/if}
				</div>
			</div>
			<div>
				<label class="label" for="ach-max">Max Earners</label>
				<input id="ach-max" class="input" type="number" bind:value={f.max_earners} min="1" placeholder="Unlimited" />
				<p class="text-xs text-zinc-500 mt-0.5">Leave blank for unlimited</p>
			</div>
			<div class="flex items-center pt-6">
				<label class="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
					<input type="checkbox" class="accent-brand-500" bind:checked={f.is_hidden} />
					Hidden (not shown on public page)
				</label>
			</div>
		</div>

		<!-- Actions -->
		<div class="flex gap-2 pt-2 border-t border-surface-300">
			<button class="btn-primary mt-3" onclick={handleSubmit}>{editId ? 'Save Changes' : 'Create Achievement'}</button>
			<button class="btn-secondary mt-3" onclick={resetForm}>Cancel</button>
		</div>
	</div>
{/if}

<!-- ==================== ACHIEVEMENT TABLE ==================== -->
{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading achievements..." />
	</div>
{:else if achievements.length === 0}
	<EmptyState title="No achievements" description="Create your first achievement template." />
{:else}
	<div class="card p-0 overflow-hidden">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-surface-300 text-xs text-zinc-500 uppercase tracking-wider">
					<th class="px-4 py-3 text-left">Name</th>
					<th class="px-4 py-3 text-left">Category</th>
					<th class="px-4 py-3 text-left">Rarity</th>
					<th class="px-4 py-3 text-left">Trigger</th>
					<th class="px-4 py-3 text-right">Rewards</th>
					<th class="px-4 py-3 text-center">Status</th>
					<th class="px-4 py-3 text-right">Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each achievements as a (a.id)}
					<tr class="border-b border-surface-300/50 hover:bg-surface-200/50 transition-all duration-150 {!a.active ? 'opacity-50' : ''}">
						<td class="px-4 py-3">
							<p class="font-medium text-zinc-200">{a.name}</p>
							{#if a.description}
								<p class="text-xs text-zinc-500 truncate max-w-48">{a.description}</p>
							{/if}
							{#if a.series_id}
								<p class="text-[10px] text-zinc-600">
									Series: {seriesName(a.series_id)} #{a.series_order}
								</p>
							{/if}
						</td>
						<td class="px-4 py-3 text-zinc-400">{categoryName(a.category_id)}</td>
						<td class="px-4 py-3">
							{#if a.rarity_id}
								<RarityBadge rarity={rarityName(a.rarity_id)} color={rarityColor(a.rarity_id)} />
							{:else}
								<span class="text-zinc-600">—</span>
							{/if}
						</td>
						<td class="px-4 py-3 text-xs text-zinc-400">{triggerLabel(a.trigger_type)}</td>
						<td class="px-4 py-3 text-right text-xs">
							{#if a.xp_reward > 0}<span class="text-brand-400">{a.xp_reward} {currency.primary}</span>{/if}
							{#if a.gold_reward > 0}<span class="text-gold-400 ml-1">{a.gold_reward} {currency.secondary}</span>{/if}
						</td>
						<td class="px-4 py-3 text-center">
							<span class="badge {a.active ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}">
								{a.active ? 'Active' : 'Off'}
							</span>
							{#if a.is_hidden}<span class="badge bg-zinc-500/10 text-zinc-500 ml-1">Hidden</span>{/if}
						</td>
						<td class="px-4 py-3 text-right">
							<div class="flex gap-1 justify-end">
								<button class="btn-secondary text-xs !px-2 !py-1" onclick={() => startEdit(a)}>Edit</button>
								<button class="text-xs {a.active ? 'btn-danger' : 'btn-secondary'} !px-2 !py-1"
									onclick={() => toggleActive(a)}>
									{a.active ? 'Off' : 'On'}
								</button>
								<button class="btn-danger text-xs !px-2 !py-1" onclick={() => deleteAchievement(a)}>Del</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<!-- Media Picker Modal -->
{#if showMediaPicker}
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
	role="dialog" aria-modal="true" aria-label="Select badge image">
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="bg-surface-800 border border-surface-600 rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
		onkeydown={(e) => { if (e.key === 'Escape') showMediaPicker = false; }}>
		<div class="flex items-center justify-between p-4 border-b border-surface-600">
			<h3 class="text-lg font-semibold">Select Badge Image</h3>
			<button class="text-zinc-400 hover:text-zinc-200" onclick={() => { showMediaPicker = false; }}>&times;</button>
		</div>
		<div class="p-4 overflow-y-auto flex-1">
			{#if mediaFiles.length === 0}
				<p class="text-zinc-500 text-center py-8">No media files. Upload images on the <a href="/admin/media" class="text-brand-400 underline">Media</a> page first.</p>
			{:else}
				<div class="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2">
					{#each mediaFiles as mf}
						<button type="button" class="group relative aspect-square rounded border border-surface-600
							hover:border-brand-400 overflow-hidden transition-colors focus:outline-none focus:ring-2 focus:ring-brand-400"
							onclick={() => selectMedia(mf.url)}>
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
			<button class="btn-secondary text-xs" onclick={() => { showMediaPicker = false; }}>Cancel</button>
		</div>
	</div>
</div>
{/if}

<!-- end -->