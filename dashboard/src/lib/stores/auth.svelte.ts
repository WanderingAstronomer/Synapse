/**
 * Auth store — rune-based singleton.
 *
 * Manages user authentication state with server-verified login,
 * proactive token-expiry detection, and reactive user/admin getters.
 *
 * Token lifecycle
 * ---------------
 * JWTs carry an `exp` claim (12 h from issuance).  Rather than waiting
 * for a 401 to surface mid-session, we decode the payload client-side
 * (no crypto — just base64) and run a 30 s heartbeat that triggers
 * `expiredLogout()` once the token is within 60 s of expiry.
 */
import { api } from '$lib/api';
import { flash } from '$lib/stores/flash.svelte';
import { TOKEN_KEY } from '$lib/constants';

export interface AuthUser {
	id: string;
	username: string;
	avatar: string | null;
	is_admin: boolean;
}

// ---------------------------------------------------------------------------
//  JWT payload helpers (decode only — no signature verification)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
//  JWT payload helpers (decode only — no signature verification)
// ---------------------------------------------------------------------------

/** Decode the base64url payload section of a JWT. Returns null on failure. */
function parseTokenPayload(token: string): Record<string, unknown> | null {
	try {
		const parts = token.split('.');
		if (parts.length !== 3) return null;
		// base64url → base64
		const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
		return JSON.parse(atob(b64));
	} catch {
		return null;
	}
}

/** Seconds until the JWT expires. Negative = already expired. */
function tokenSecondsRemaining(token: string): number {
	const payload = parseTokenPayload(token);
	if (!payload || typeof payload.exp !== 'number') return -1;
	return payload.exp - Date.now() / 1000;
}

// ---------------------------------------------------------------------------
//  Reactive state
// ---------------------------------------------------------------------------

/** Guard to prevent cascading 401 redirects. */
let _expiredRedirecting = false;

let _user = $state<AuthUser | null>(null);
let _loading = $state(true);

/** Handle returned by setInterval for the expiry heartbeat. */
let _expiryTimer: ReturnType<typeof setInterval> | null = null;

/** Minimum seconds remaining before we proactively log out. */
const EXPIRY_BUFFER_SECONDS = 60;

/** How often (ms) the heartbeat checks the token. */
const EXPIRY_CHECK_INTERVAL_MS = 30_000;

function _startExpiryHeartbeat() {
	_stopExpiryHeartbeat();
	_expiryTimer = setInterval(() => {
		const token = localStorage.getItem(TOKEN_KEY);
		if (!token) {
			_stopExpiryHeartbeat();
			return;
		}
		if (tokenSecondsRemaining(token) < EXPIRY_BUFFER_SECONDS) {
			auth.expiredLogout();
		}
	}, EXPIRY_CHECK_INTERVAL_MS);
}

function _stopExpiryHeartbeat() {
	if (_expiryTimer !== null) {
		clearInterval(_expiryTimer);
		_expiryTimer = null;
	}
}

// ---------------------------------------------------------------------------
//  Public API
// ---------------------------------------------------------------------------

export const auth = {
	get user() {
		return _user;
	},
	get isAdmin() {
		return _user?.is_admin ?? false;
	},
	get loading() {
		return _loading;
	},

	async init() {
		const token =
			typeof localStorage !== 'undefined'
				? localStorage.getItem(TOKEN_KEY)
				: null;
		if (!token) {
			_loading = false;
			return;
		}

		// Fast-reject tokens that have already expired (no network round-trip)
		if (tokenSecondsRemaining(token) < EXPIRY_BUFFER_SECONDS) {
			localStorage.removeItem(TOKEN_KEY);
			_user = null;
			_loading = false;
			return;
		}

		try {
			const user = await api.getMe();
			_user = user;
			_startExpiryHeartbeat();
		} catch {
			// Token invalid or expired
			localStorage.removeItem(TOKEN_KEY);
			_user = null;
		} finally {
			_loading = false;
		}
	},

	/**
	 * Log in with a token received from the OAuth callback.
	 * Always verifies the token server-side via getMe() before
	 * granting admin privileges. Returns the verified user or null.
	 */
	async login(token: string): Promise<AuthUser | null> {
		localStorage.setItem(TOKEN_KEY, token);
		_loading = true;
		try {
			const user = await api.getMe();
			_user = user;
			_startExpiryHeartbeat();
			return user;
		} catch {
			// Token invalid — clear it
			localStorage.removeItem(TOKEN_KEY);
			_user = null;
			_stopExpiryHeartbeat();
			return null;
		} finally {
			_loading = false;
		}
	},

	logout() {
		localStorage.removeItem(TOKEN_KEY);
		_user = null;
		_stopExpiryHeartbeat();
	},

	/**
	 * Called by the 401 handler when a token has expired mid-session.
	 * Clears credentials, flashes a message, and redirects to /.
	 * Deduplicates to prevent cascade from multiple concurrent requests.
	 */
	expiredLogout() {
		if (_expiredRedirecting) return;
		_expiredRedirecting = true;
		localStorage.removeItem(TOKEN_KEY);
		_user = null;
		_stopExpiryHeartbeat();
		flash.warning('Your session has expired. Please sign in again.');
		// Use setTimeout so the flash store has time to update before navigation
		setTimeout(() => {
			_expiredRedirecting = false;
			window.location.href = '/';
		}, 100);
	},
};
