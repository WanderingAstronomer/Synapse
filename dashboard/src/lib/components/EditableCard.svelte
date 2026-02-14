<script lang="ts">
	import { editMode, saveCard } from '$lib/stores/editMode.svelte';
	import { api } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import type { CardConfig } from '$lib/api';

	interface Props {
		card: CardConfig;
		showTitles?: boolean;
		/** Visual indicator: 'before' | 'after' | null — shows drop zone line */
		dropIndicator?: 'before' | 'after' | null;
		onreorder?: (draggedId: string, targetId: string) => void;
		ondelete?: (cardId: string) => void;
		onmoveup?: (cardId: string) => void;
		onmovedown?: (cardId: string) => void;
		children: import('svelte').Snippet;
	}

	let { card, showTitles = true, dropIndicator = null, onreorder, ondelete, onmoveup, onmovedown, children }: Props = $props();

	let isAdmin = $derived(editMode.canEdit);
	let isHovered = $state(false);
	let isActive = $derived(editMode.activeCardId === card.id);

	// Confirm modal state for delete
	let deleteModalOpen = $state(false);

	function openPropertyPanel() {
		editMode.activeCardId = card.id;
	}

	function handleTitleBlur(e: FocusEvent) {
		const el = e.target as HTMLElement;
		const newTitle = el.textContent?.trim() || '';
		if (newTitle !== (card.title || '')) {
			saveCard(card.id, { title: newTitle });
		}
	}

	function handleSubtitleBlur(e: FocusEvent) {
		const el = e.target as HTMLElement;
		const newSubtitle = el.textContent?.trim() || '';
		if (newSubtitle !== (card.subtitle || '')) {
			saveCard(card.id, { subtitle: newSubtitle });
		}
	}

	function handleTitleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			(e.target as HTMLElement).blur();
		}
	}

	function toggleVisibility() {
		const prev = card.visible;
		card.visible = !prev; // optimistic local update
		saveCard(card.id, { visible: !prev });
	}

	function cycleGridSpan() {
		const prev = card.grid_span;
		const next = (prev % 3) + 1;
		card.grid_span = next; // optimistic local update
		saveCard(card.id, { grid_span: next });
	}

	async function handleDelete() {
		deleteModalOpen = true;
	}

	async function confirmDelete() {
		try {
			await api.admin.deleteCard(card.id);
			flash.success('Card deleted');
			ondelete?.(card.id);
		} catch (err: any) {
			flash.error(`Failed to delete card: ${err.message}`);
		}
	}

	// ---- Drag-and-drop ----
	function handleDragStart(e: DragEvent) {
		e.dataTransfer?.setData('application/x-card-id', card.id);
		if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
	}

	function handleDragOver(e: DragEvent) {
		if (!isAdmin) return;
		const id = e.dataTransfer?.types.includes('application/x-card-id');
		if (id) e.preventDefault(); // allow drop
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		const draggedId = e.dataTransfer?.getData('application/x-card-id');
		if (draggedId && draggedId !== card.id && onreorder) {
			onreorder(draggedId, card.id);
		}
	}
</script>

<div
	class="editable-card"
	class:edit-active={isAdmin}
	class:card-selected={isActive}
	class:card-hidden={isAdmin && !card.visible}
	class:drop-before={dropIndicator === 'before'}
	class:drop-after={dropIndicator === 'after'}
	style:grid-column={`span ${card.grid_span}`}
	role="article"
	onmouseenter={() => { if (isAdmin) isHovered = true; }}
	onmouseleave={() => { isHovered = false; }}
	ondragover={handleDragOver}
	ondrop={handleDrop}
>
	<!-- Edit overlay (drag handle, settings gear) — visible on hover for admins -->
	{#if isAdmin}
		<div class="edit-overlay" class:visible={isHovered || isActive}>
			<!-- Drag handle -->
			<div
				class="drag-handle"
				title="Drag to reorder"
				role="button"
				tabindex="0"
				draggable="true"
				ondragstart={handleDragStart}
			>
				<span class="drag-dots">⠿</span>
			</div>

			<!-- Top-right controls -->
			<div class="edit-controls-top">
				{#if onmoveup}
					<button
						class="edit-btn"
						title="Move card up"
						aria-label="Move card up"
						onclick={() => onmoveup(card.id)}
					>
						▲
					</button>
				{/if}
				{#if onmovedown}
					<button
						class="edit-btn"
						title="Move card down"
						aria-label="Move card down"
						onclick={() => onmovedown(card.id)}
					>
						▼
					</button>
				{/if}
				<button
					class="edit-btn"
					title={card.visible ? 'Hide card' : 'Show card'}
					onclick={toggleVisibility}
				>
					{card.visible ? '👁' : '👁‍🗨'}
				</button>
				<button
					class="edit-btn"
					title="Width: {card.grid_span}/3 → {(card.grid_span % 3) + 1}/3"
					onclick={cycleGridSpan}
				>
					↔
				</button>
				<button
					class="edit-btn"
					title="Card settings"
					onclick={openPropertyPanel}
				>
					⚙
				</button>
				<button
					class="edit-btn edit-btn-danger"
					title="Delete card"
					onclick={handleDelete}
				>
					✕
				</button>
			</div>
		</div>

		<!-- Editable title (if card has one) -->
		{#if showTitles && card.title !== null}
			<div class="editable-title-wrapper">
				<span
					class="editable-text title"
					contenteditable="true"
					role="textbox"
					aria-label="Edit card title"
					aria-multiline="false"
					tabindex={0}
					onblur={handleTitleBlur}
					onkeydown={handleTitleKeydown}
				>{card.title || 'Untitled'}</span>
			</div>
		{/if}

		<!-- Editable subtitle -->
		{#if showTitles && card.subtitle !== null}
			<div class="editable-subtitle-wrapper">
				<span
					class="editable-text subtitle"
					contenteditable="true"
					role="textbox"
					aria-label="Edit card subtitle"
					aria-multiline="false"
					tabindex={0}
					onblur={handleSubtitleBlur}
					onkeydown={handleTitleKeydown}
				>{card.subtitle || ''}</span>
			</div>
		{/if}
	{/if}

	<!-- Actual card content (slot) -->
	<div class="card-content" class:dimmed={isAdmin && !card.visible}>
		{@render children()}
	</div>
</div>

<ConfirmModal
	bind:open={deleteModalOpen}
	title="Delete Card"
	message="Remove this card? This cannot be undone."
	confirmLabel="Delete"
	danger={true}
	onconfirm={confirmDelete}
	oncancel={() => {}}
/>

<style>
	.editable-card {
		position: relative;
		border-radius: 0.75rem;
		transition: all 0.2s;
	}

	.editable-card.edit-active {
		outline: 2px dashed transparent;
		outline-offset: 4px;
	}

	.editable-card.edit-active:hover {
		outline-color: rgba(124, 58, 237, 0.4);
	}

	.editable-card.card-selected {
		outline: 2px solid rgba(124, 58, 237, 0.7) !important;
	}

	.editable-card.card-hidden {
		opacity: 0.4;
	}

	.editable-card.drop-before {
		outline: 2px solid rgba(124, 58, 237, 0.6) !important;
		outline-offset: 4px;
	}

	.editable-card.drop-after {
		outline: 2px solid rgba(124, 58, 237, 0.6) !important;
		outline-offset: 4px;
	}

	.edit-overlay {
		position: absolute;
		inset: 0;
		z-index: 10;
		pointer-events: none;
		opacity: 0;
		transition: opacity 0.15s;
	}

	.edit-overlay.visible {
		opacity: 1;
	}

	.drag-handle {
		position: absolute;
		top: 0.5rem;
		left: 0.5rem;
		pointer-events: auto;
		cursor: grab;
		padding: 0.25rem;
		border-radius: 4px;
		background: rgba(0, 0, 0, 0.4);
		backdrop-filter: blur(4px);
		color: #a1a1aa;
		font-size: 1.2rem;
		line-height: 1;
		transition: color 0.15s;
	}
	.drag-handle:hover {
		color: white;
	}
	.drag-dots {
		display: block;
		letter-spacing: -1px;
	}

	.edit-controls-top {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		display: flex;
		gap: 0.25rem;
		pointer-events: auto;
	}

	.edit-btn {
		width: 2rem;
		height: 2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.4);
		backdrop-filter: blur(4px);
		border: 1px solid rgba(255, 255, 255, 0.08);
		cursor: pointer;
		font-size: 1rem;
		color: #a1a1aa;
		transition: all 0.15s;
	}
	.edit-btn:hover {
		background: rgba(0, 0, 0, 0.6);
		border-color: rgba(124, 58, 237, 0.5);
		color: white;
	}
	.edit-btn-danger:hover {
		border-color: rgba(239, 68, 68, 0.5);
		color: #ef4444;
	}

	.editable-title-wrapper,
	.editable-subtitle-wrapper {
		position: relative;
		z-index: 5;
	}

	.editable-text {
		display: inline-block;
		border-bottom: 1px dashed rgba(124, 58, 237, 0.4);
		outline: none;
		min-width: 2rem;
		padding: 0 0.15rem;
		cursor: text;
		transition: border-color 0.15s;
	}
	.editable-text:focus {
		border-bottom-color: rgba(124, 58, 237, 0.8);
		background: rgba(124, 58, 237, 0.05);
		border-radius: 2px;
	}

	.editable-text.title {
		font-size: 1.1rem;
		font-weight: 600;
		color: #e4e4e7;
	}

	.editable-text.subtitle {
		font-size: 0.85rem;
		color: #a1a1aa;
	}

	.card-content {
		transition: opacity 0.2s;
	}
	.card-content.dimmed {
		opacity: 0.3;
		pointer-events: none;
	}
</style>
