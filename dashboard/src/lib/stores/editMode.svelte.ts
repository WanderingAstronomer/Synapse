/**
 * Edit-mode store — rune-based singleton.
 *
 * Controls admin editing state: whether edit mode is active
 * (derived from auth), which card is selected, and persists
 * card/layout changes to the backend.
 */
import { api } from '$lib/api';
import { auth } from '$lib/stores/auth.svelte';
import { flash } from '$lib/stores/flash.svelte';

// ---------------------------------------------------------------------------
// Active property panel — which card is being edited
// ---------------------------------------------------------------------------
let _activeCardId = $state<string | null>(null);

export const editMode = {
	/**
	 * Whether the user can perform admin edits (must be admin).
	 * Replaces the old `canEdit = derived(isAdmin, x => x)`.
	 */
	get canEdit() {
		return auth.isAdmin;
	},

	get activeCardId() {
		return _activeCardId;
	},
	set activeCardId(id: string | null) {
		_activeCardId = id;
	},
};

// ---------------------------------------------------------------------------
// Immediate card saves (debounced)
// ---------------------------------------------------------------------------
const _cardTimers = new Map<string, ReturnType<typeof setTimeout>>();

/**
 * Save a card update (debounced 500ms per card).
 * On failure, flashes an error so the user knows the server rejected the change.
 */
export function saveCard(cardId: string, patch: Record<string, unknown>) {
	const existing = _cardTimers.get(cardId);
	if (existing) clearTimeout(existing);
	_cardTimers.set(
		cardId,
		setTimeout(async () => {
			_cardTimers.delete(cardId);
			try {
				await api.admin.updateCard(cardId, patch);
			} catch (err) {
				console.error(`Failed to save card ${cardId}:`, err);
				flash.error('Card update failed. Your change may not have been saved.');
			}
		}, 500),
	);
}

/**
 * Save a layout update (e.g. card_order after drag).
 * Returns true on success, false on failure (with flash).
 */
export async function saveLayout(
	pageSlug: string,
	patch: { display_name?: string; card_order?: string[] },
): Promise<boolean> {
	try {
		await api.admin.updateLayout(pageSlug, patch);
		return true;
	} catch (err) {
		console.error(`Failed to save layout ${pageSlug}:`, err);
		flash.error('Layout update failed. Reloading to restore server state.');
		return false;
	}
}
