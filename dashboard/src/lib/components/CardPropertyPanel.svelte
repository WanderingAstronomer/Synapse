<script lang="ts">
	import { editMode, saveCard } from '$lib/stores/editMode.svelte';
	import { api, type CardConfig } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';

	interface Props {
		cards: CardConfig[];
		ondelete?: (cardId: string) => void;
	}

	let { cards, ondelete }: Props = $props();

	let uploading = $state(false);
	let deleteModalOpen = $state(false);

	let activeCard = $derived(cards.find((c) => c.id === editMode.activeCardId) || null);
	let isOpen = $derived(editMode.canEdit && activeCard !== null);

	function close() {
		editMode.activeCardId = null;
	}

	function updateField(field: keyof CardConfig, value: unknown) {
		if (!activeCard) return;
		saveCard(activeCard.id, { [field]: value } as Partial<CardConfig>);
	}

	function updateConfigField(key: string, value: unknown) {
		if (!activeCard) return;
		const newConfig = { ...(activeCard.config_json || {}), [key]: value };
		saveCard(activeCard.id, { config_json: newConfig });
	}

	async function handleImageUpload(e: Event, configKey: string) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;

		uploading = true;
		try {
			const result = await api.admin.uploadFile(file);
			updateConfigField(configKey, result.url);
			flash.success('Image uploaded');
		} catch (err: any) {
			flash.error(`Upload failed: ${err.message}`);
		} finally {
			uploading = false;
		}
	}

	async function deleteCard() {
		if (!activeCard) return;
		deleteModalOpen = true;
	}

	async function confirmDeleteCard() {
		if (!activeCard) return;
		const cardId = activeCard.id;
		try {
			await api.admin.deleteCard(cardId);
			flash.success('Card removed');
			close();
			// Notify parent to update local state
			ondelete?.(cardId);
		} catch (err: any) {
			flash.error(`Delete failed: ${err.message}`);
		}
	}

	// Available metric keys for metric cards (loaded from API)
	let metricOptions = $state<{ key: string; label: string; icon?: string }[]>([
		{ key: 'total_members', label: 'Total Members' },
		{ key: 'total_xp', label: 'Total XP' },
		{ key: 'total_gold', label: 'Total Gold' },
		{ key: 'active_users_7d', label: 'Active Users (7d)' },
		{ key: 'top_level', label: 'Top Level' },
		{ key: 'total_achievements', label: 'Achievements Earned' },
	]);

	// Fetch available metrics from API (replaces defaults when available)
	import { onMount } from 'svelte';
	onMount(() => {
		fetch('/api/metrics/available')
			.then((r) => r.ok ? r.json() : null)
			.then((data) => { if (data) metricOptions = data; })
			.catch(() => {});
	});

	// Grid span labels
	const spanLabels: Record<number, string> = { 1: 'Small (1 col)', 2: 'Medium (2 col)', 3: 'Full (3 col)' };
</script>

<!-- Backdrop -->
{#if isOpen}
	<div class="panel-backdrop" onclick={close} role="presentation"></div>
{/if}

<!-- Side panel -->
<div class="property-panel" class:open={isOpen}>
	{#if activeCard}
		<div class="panel-header">
			<h3 class="text-sm font-semibold text-zinc-200">Card Settings</h3>
			<button class="panel-close" onclick={close}>✕</button>
		</div>

		<div class="panel-body">
			<!-- Card type info -->
			<div class="field-group">
				<!-- svelte-ignore a11y_label_has_associated_control -->
				<label class="field-label">Type</label>
				<div class="field-value">{activeCard.card_type.replace(/_/g, ' ')}</div>
			</div>

			<!-- Title -->
			<div class="field-group">
				<label class="field-label" for="card-title">Title</label>
				<input
					id="card-title"
					type="text"
					class="input"
					value={activeCard.title || ''}
					oninput={(e) => updateField('title', (e.target as HTMLInputElement).value)}
				/>
			</div>

			<!-- Subtitle -->
			<div class="field-group">
				<label class="field-label" for="card-subtitle">Subtitle</label>
				<input
					id="card-subtitle"
					type="text"
					class="input"
					value={activeCard.subtitle || ''}
					oninput={(e) => updateField('subtitle', (e.target as HTMLInputElement).value)}
				/>
			</div>

			<!-- Grid span (not for hero — always full width) -->
			{#if activeCard.card_type !== 'hero_banner'}
				<div class="field-group">
					<!-- svelte-ignore a11y_label_has_associated_control -->
					<label class="field-label">Width</label>
					<div class="span-selector">
						{#each [1, 2, 3] as span}
							<button
								class="span-btn"
								class:active={activeCard.grid_span === span}
								onclick={() => updateField('grid_span', span)}
							>
								{spanLabels[span]}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Visibility -->
			<div class="field-group">
				<!-- svelte-ignore a11y_label_has_associated_control -->
				<label class="field-label">Visibility</label>
				<label class="toggle-label">
					<input
						type="checkbox"
						checked={activeCard.visible}
						onchange={() => updateField('visible', !activeCard.visible)}
					/>
					<span>{activeCard.visible ? 'Visible' : 'Hidden'}</span>
				</label>
			</div>

			<!-- Type-specific fields -->
			{#if activeCard.card_type === 'metric'}
				<div class="field-group">
					<label class="field-label" for="metric-key">Metric</label>
					<select
						id="metric-key"
						class="input"
						value={activeCard.config_json?.metric_key || ''}
						onchange={(e) => updateConfigField('metric_key', (e.target as HTMLSelectElement).value)}
					>
						<option value="">Select metric...</option>
						{#each metricOptions as opt}
							<option value={opt.key}>{opt.label}</option>
						{/each}
					</select>
				</div>
			{/if}

			{#if activeCard.card_type === 'hero_banner'}
				<div class="field-group">
					<!-- svelte-ignore a11y_label_has_associated_control -->
					<label class="field-label">Background Image</label>
					<input
						type="file"
						accept="image/*"
						class="file-input"
						disabled={uploading}
						onchange={(e) => handleImageUpload(e, 'background_image')}
					/>
					{#if activeCard.config_json?.background_image}
						<div class="image-preview">
							<img src={activeCard.config_json.background_image as string} alt="Background" />
						</div>
					{/if}
				</div>

				<div class="field-group">
					<label class="field-label" for="bg-color">Background Color</label>
					<div class="color-row">
						<input
							id="bg-color"
							type="color"
							value={activeCard.config_json?.background_color as string || '#1e1b4b'}
							oninput={(e) => updateConfigField('background_color', (e.target as HTMLInputElement).value)}
						/>
						<span class="color-hex">{activeCard.config_json?.background_color || '#1e1b4b'}</span>
					</div>
				</div>
			{/if}

			<!-- Danger zone -->
			<div class="danger-section">
				<button class="btn-danger" onclick={deleteCard}>
					Delete Card
				</button>
			</div>
		</div>
	{/if}
</div>

<ConfirmModal
	bind:open={deleteModalOpen}
	title="Delete Card"
	message="Remove this card? This cannot be undone."
	confirmLabel="Delete"
	danger={true}
	onconfirm={confirmDeleteCard}
	oncancel={() => {}}
/>

<style>
	.panel-backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
		background: rgba(0, 0, 0, 0.3);
		backdrop-filter: blur(2px);
	}

	.property-panel {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: 22rem;
		z-index: 45;
		background: #18181b;
		border-left: 1px solid #27272a;
		transform: translateX(100%);
		transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
		display: flex;
		flex-direction: column;
		overflow-y: auto;
	}

	.property-panel.open {
		transform: translateX(0);
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid #27272a;
	}

	.panel-close {
		width: 1.75rem;
		height: 1.75rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 6px;
		background: transparent;
		border: none;
		color: #71717a;
		cursor: pointer;
		font-size: 0.9rem;
		transition: all 0.15s;
	}
	.panel-close:hover {
		background: #27272a;
		color: #f4f4f5;
	}

	.panel-body {
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.field-group {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.field-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: #a1a1aa;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.field-value {
		font-size: 0.85rem;
		color: #e4e4e7;
		text-transform: capitalize;
		background: #27272a;
		padding: 0.4rem 0.6rem;
		border-radius: 6px;
	}

	.span-selector {
		display: flex;
		gap: 0.25rem;
	}

	.span-btn {
		flex: 1;
		padding: 0.35rem 0.5rem;
		font-size: 0.7rem;
		border-radius: 6px;
		background: #27272a;
		border: 1px solid #3f3f46;
		color: #a1a1aa;
		cursor: pointer;
		transition: all 0.15s;
	}
	.span-btn.active {
		background: rgba(124, 58, 237, 0.15);
		border-color: rgba(124, 58, 237, 0.5);
		color: #c4b5fd;
	}

	.toggle-label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.85rem;
		color: #d4d4d8;
		cursor: pointer;
	}

	.color-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.color-hex {
		font-size: 0.8rem;
		font-family: 'JetBrains Mono', monospace;
		color: #a1a1aa;
	}

	.file-input {
		font-size: 0.8rem;
		color: #a1a1aa;
	}

	.image-preview {
		margin-top: 0.5rem;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid #3f3f46;
	}
	.image-preview img {
		width: 100%;
		height: 6rem;
		object-fit: cover;
	}

	.danger-section {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid #27272a;
	}
</style>
