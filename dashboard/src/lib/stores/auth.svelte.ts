/**
 * Auth store — rune-based singleton.
 *
 * Manages user authentication state with server-verified login,
 * expired session handling, and reactive user/admin getters.
 */
import { api } from '$lib/api';
import { flash } from '$lib/stores/flash.svelte';

export interface AuthUser {
	id: string;
	username: string;
	avatar: string | null;
	is_admin: boolean;
}

/** Guard to prevent cascading 401 redirects. */
let _expiredRedirecting = false;

let _user = $state<AuthUser | null>(null);
let _loading = $state(true);

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
				? localStorage.getItem('synapse_token')
				: null;
		if (!token) {
			_loading = false;
			return;
		}
		try {
			const user = await api.getMe();
			_user = user;
		} catch {
			// Token invalid or expired
			localStorage.removeItem('synapse_token');
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
		localStorage.setItem('synapse_token', token);
		_loading = true;
		try {
			const user = await api.getMe();
			_user = user;
			return user;
		} catch {
			// Token invalid — clear it
			localStorage.removeItem('synapse_token');
			_user = null;
			return null;
		} finally {
			_loading = false;
		}
	},

	logout() {
		localStorage.removeItem('synapse_token');
		_user = null;
	},

	/**
	 * Called by the 401 handler when a token has expired mid-session.
	 * Clears credentials, flashes a message, and redirects to /.
	 * Deduplicates to prevent cascade from multiple concurrent requests.
	 */
	expiredLogout() {
		if (_expiredRedirecting) return;
		_expiredRedirecting = true;
		localStorage.removeItem('synapse_token');
		_user = null;
		flash.warning('Your session has expired. Please sign in again.');
		// Use setTimeout so the flash store has time to update before navigation
		setTimeout(() => {
			_expiredRedirecting = false;
			window.location.href = '/';
		}, 100);
	},
};
