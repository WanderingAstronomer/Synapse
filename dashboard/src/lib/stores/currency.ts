import { writable, derived } from 'svelte/store';
import { api } from '$lib/api';

/**
 * Configurable currency display names.
 *
 * Defaults to "XP" / "Gold" but pulls actual names from
 * the public settings endpoint once loaded.
 */
interface CurrencyLabels {
	primary: string;   // e.g. "XP", "Honor", "Karma"
	secondary: string; // e.g. "Gold", "Loot", "Credits"
}

function createCurrencyStore() {
	const { subscribe, set } = writable<CurrencyLabels>({
		primary: 'XP',
		secondary: 'Gold',
	});

	let loaded = false;

	async function fetchLabels() {
		try {
			const settings = await api.getPublicSettings();
			const primary =
				(settings['economy.primary_currency_name'] as string) || 'XP';
			const secondary =
				(settings['economy.secondary_currency_name'] as string) || 'Gold';
			set({ primary, secondary });
		} catch {
			// Keep defaults on error
		}
	}

	return {
		subscribe,

		/** Fetch currency names from public settings (call once on app init). */
		async init() {
			if (loaded) return;
			await fetchLabels();
			loaded = true;
		},

		/** Force a re-fetch of currency names (call after settings save). */
		async refresh() {
			await fetchLabels();
			loaded = true;
		},
	};
}

export const currencyLabels = createCurrencyStore();

/** Convenience derived stores for individual labels */
export const primaryCurrency = derived(currencyLabels, ($c) => $c.primary);
export const secondaryCurrency = derived(currencyLabels, ($c) => $c.secondary);
