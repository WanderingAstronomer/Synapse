/**
 * Site settings store — rune-based singleton.
 *
 * Holds public site settings (display titles, favicon, etc.)
 * loaded once by the root layout. Consumed by Sidebar, pages, etc.
 */
import { api } from '$lib/api';

let _settings = $state<Record<string, unknown>>({});

export const siteSettings = {
	/** Raw settings map — populated by init(). */
	get settings() {
		return _settings;
	},

	/** Fetch public settings and populate the store. Call once from root layout. */
	async init(): Promise<Record<string, unknown>> {
		try {
			const settings = await api.getPublicSettings();
			_settings = settings as Record<string, unknown>;
			return _settings;
		} catch {
			return {};
		}
	},

	// ---- Convenience helpers ----

	/**
	 * Page display title — reads `display.<slug>_title` with a fallback.
	 * Reactive when called inside $derived or template expressions
	 * because it reads from $state under the hood.
	 */
	pageTitle(slug: string, fallback: string): string {
		const val = _settings[`display.${slug}_title`];
		return typeof val === 'string' && val ? val : fallback;
	},

	/** Favicon URL from settings, or null. */
	get faviconUrl(): string | null {
		return (_settings['display.favicon_url'] as string) || null;
	},

	/** Primary brand color from settings, or null. */
	get primaryColor(): string | null {
		return (_settings['display.primary_color'] as string) || null;
	},
};
