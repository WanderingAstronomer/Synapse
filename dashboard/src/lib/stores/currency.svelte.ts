/**
 * Currency label store — rune-based singleton.
 *
 * Provides configurable display names for primary (XP) and
 * secondary (Gold) currencies, fetched from public settings.
 */
import { api } from '$lib/api';

let _primary = $state('XP');
let _secondary = $state('Gold');
let _loaded = false;

async function fetchLabels() {
	try {
		const settings = await api.getPublicSettings();
		_primary = (settings['economy.primary_currency_name'] as string) || 'XP';
		_secondary = (settings['economy.secondary_currency_name'] as string) || 'Gold';
	} catch {
		// Keep defaults on error
	}
}

export const currency = {
	/** Reactive primary currency label (e.g. "XP", "Honor"). */
	get primary() {
		return _primary;
	},

	/** Reactive secondary currency label (e.g. "Gold", "Credits"). */
	get secondary() {
		return _secondary;
	},

	/** Fetch currency names from public settings (call once on app init). */
	async init() {
		if (_loaded) return;
		await fetchLabels();
		_loaded = true;
	},

	/** Force a re-fetch of currency names (call after settings save). */
	async refresh() {
		await fetchLabels();
		_loaded = true;
	},
};
