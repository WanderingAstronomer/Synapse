<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type AdminAchievement } from '$lib/api';
	import { flash } from '$lib/stores/flash';
	import RarityBadge from '$lib/components/RarityBadge.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { capitalize } from '$lib/utils';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';

	let achievements = $state<AdminAchievement[]>([]);
	let loading = $state(true);
	let showForm = $state(false);
	let editId = $state<number | null>(null);

	// Form
	let f = $state({
		name: '', description: '', category: 'social',
		requirement_type: 'custom', requirement_scope: 'season',
		requirement_field: '', requirement_value: 0,
		xp_reward: 0, gold_reward: 0, badge_image_url: '',
		rarity: 'common',
	});

	const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
	const CATEGORIES = ['social', 'coding', 'engagement', 'special'];

	async function load() {
		try {
			const res = await api.admin.getAchievements();
			achievements = res.achievements;
		} catch (e) { flash.error('Failed to load achievements'); }
		finally { loading = false; }
	}

	onMount(load);

	function resetForm() {
		f = { name: '', description: '', category: 'social', requirement_type: 'custom',
			requirement_scope: 'season', requirement_field: '', requirement_value: 0,
			xp_reward: 0, gold_reward: 0, badge_image_url: '', rarity: 'common' };
		showForm = false;
		editId = null;
	}

	function startEdit(a: AdminAchievement) {
		editId = a.id;
		f = {
			name: a.name, description: a.description || '', category: a.category,
			requirement_type: a.requirement_type, requirement_scope: a.requirement_scope,
			requirement_field: a.requirement_field || '', requirement_value: a.requirement_value || 0,
			xp_reward: a.xp_reward, gold_reward: a.gold_reward,
			badge_image_url: a.badge_image_url || '', rarity: a.rarity,
		};
		showForm = false;
	}

	async function handleSubmit() {
		if (!f.name.trim()) { flash.warning('Name is required'); return; }
		try {
			if (editId) {
				await api.admin.updateAchievement(editId, {
					...f, name: f.name.trim(), description: f.description.trim() || undefined,
					requirement_field: f.requirement_field || undefined,
					badge_image_url: f.badge_image_url || undefined,
				});
				flash.success('Achievement updated');
			} else {
				await api.admin.createAchievement({
					...f, name: f.name.trim(), description: f.description.trim() || undefined,
					requirement_field: f.requirement_field || undefined,
					badge_image_url: f.badge_image_url || undefined,
				});
				flash.success(`Achievement "${f.name}" created`);
			}
			resetForm();
			await load();
		} catch (e: any) { flash.error(e.message || 'Save failed'); }
	}

	async function toggleActive(a: AdminAchievement) {
		try {
			await api.admin.updateAchievement(a.id, { active: !a.active });
			flash.success(a.active ? 'Deactivated' : 'Activated');
			await load();
		} catch (e: any) { flash.error(e.message); }
	}
</script>

<svelte:head><title>Admin: Achievements — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">🎖️ Achievements</h1>
		<p class="text-sm text-zinc-500 mt-1">Define badges and their unlock requirements.</p>
	</div>
	<button class="btn-primary" onclick={() => { resetForm(); showForm = !showForm; }}>
		+ New Achievement
	</button>
</div>

{#if showForm || editId !== null}
	<div class="card mb-6 animate-slide-up">
		<h3 class="text-sm font-semibold text-zinc-300 mb-4">{editId ? 'Edit Achievement' : 'New Achievement'}</h3>
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			<div>
				<label class="label" for="ach-name">Name</label>
				<input id="ach-name" class="input" bind:value={f.name} placeholder="First Steps" />
			</div>
			<div>
				<label class="label" for="ach-category">Category</label>
				<select id="ach-category" class="input" bind:value={f.category}>
					{#each CATEGORIES as c}<option value={c}>{capitalize(c)}</option>{/each}
				</select>
			</div>
			<div>
				<label class="label" for="ach-rarity">Rarity</label>
				<select id="ach-rarity" class="input" bind:value={f.rarity}>
					{#each RARITIES as r}<option value={r}>{capitalize(r)}</option>{/each}
				</select>
			</div>
			<div class="sm:col-span-2 lg:col-span-3">
				<label class="label" for="ach-desc">Description</label>
				<input id="ach-desc" class="input" bind:value={f.description} placeholder="Send your first message" />
			</div>
			<div>
				<label class="label" for="ach-req-type">Requirement Type</label>
				<input id="ach-req-type" class="input" bind:value={f.requirement_type} placeholder="custom" />
			</div>
			<div>
				<label class="label" for="ach-req-field">Requirement Field</label>
				<input id="ach-req-field" class="input" bind:value={f.requirement_field} placeholder="messages_sent" />
			</div>
			<div>
				<label class="label" for="ach-req-value">Requirement Value</label>
				<input id="ach-req-value" class="input" type="number" bind:value={f.requirement_value} />
			</div>
			<div>
				<label class="label" for="ach-xp">XP Reward</label>
				<input id="ach-xp" class="input" type="number" bind:value={f.xp_reward} />
			</div>
			<div>
				<label class="label" for="ach-gold">Gold Reward</label>
				<input id="ach-gold" class="input" type="number" bind:value={f.gold_reward} />
			</div>
			<div>
				<label class="label" for="ach-badge">Badge Image URL</label>
				<input id="ach-badge" class="input" bind:value={f.badge_image_url} placeholder="https://..." />
			</div>
		</div>
		<div class="flex gap-2 mt-4">
			<button class="btn-primary" onclick={handleSubmit}>{editId ? 'Save Changes' : 'Create'}</button>
			<button class="btn-secondary" onclick={resetForm}>Cancel</button>
		</div>
	</div>
{/if}

{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading achievements..." />
	</div>
{:else if achievements.length === 0}
	<EmptyState icon="🎖️" title="No achievements" description="Create your first achievement template." />
{:else}
	<div class="card p-0 overflow-hidden">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-surface-300 text-xs text-zinc-500 uppercase tracking-wider">
					<th class="px-4 py-3 text-left">Name</th>
					<th class="px-4 py-3 text-left">Category</th>
					<th class="px-4 py-3 text-left">Rarity</th>
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
						</td>
						<td class="px-4 py-3 text-zinc-400">{capitalize(a.category)}</td>
						<td class="px-4 py-3"><RarityBadge rarity={a.rarity} /></td>
						<td class="px-4 py-3 text-right text-xs">
							{#if a.xp_reward > 0}<span class="text-brand-400">{a.xp_reward} XP</span>{/if}
							{#if a.gold_reward > 0}<span class="text-gold-400 ml-1">{a.gold_reward}G</span>{/if}
						</td>
						<td class="px-4 py-3 text-center">
							<span class="badge {a.active ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}">
								{a.active ? 'Active' : 'Off'}
							</span>
						</td>
						<td class="px-4 py-3 text-right">
							<div class="flex gap-1 justify-end">
								<button class="btn-secondary text-xs !px-2 !py-1" onclick={() => startEdit(a)}>Edit</button>
								<button class="text-xs {a.active ? 'btn-danger' : 'btn-secondary'} !px-2 !py-1" onclick={() => toggleActive(a)}>
									{a.active ? 'Off' : 'On'}
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
