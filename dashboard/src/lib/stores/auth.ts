import { writable, derived } from 'svelte/store';
import { api } from '$lib/api';

interface AuthUser {
	id: string;
	username: string;
	avatar: string | null;
	is_admin: boolean;
}

function createAuthStore() {
	const { subscribe, set } = writable<AuthUser | null>(null);
	const loading = writable(true);

	return {
		subscribe,
		loading: { subscribe: loading.subscribe },

		async init() {
			const token = typeof localStorage !== 'undefined' ? localStorage.getItem('synapse_token') : null;
			if (!token) {
				loading.set(false);
				return;
			}
			try {
				const user = await api.getMe();
				set(user);
			} catch {
				// Token invalid or expired
				localStorage.removeItem('synapse_token');
				set(null);
			} finally {
				loading.set(false);
			}
		},

		login(token: string) {
			localStorage.setItem('synapse_token', token);
			// Eagerly decode for instant UI
			try {
				const payload = JSON.parse(atob(token.split('.')[1]));
				set({
					id: payload.sub,
					username: payload.username || 'Admin',
					avatar: payload.avatar || null,
					is_admin: true,
				});
			} catch {
				// Fallback to API verification
				api.getMe().then(set).catch(() => set(null));
			}
		},

		logout() {
			localStorage.removeItem('synapse_token');
			set(null);
		},
	};
}

export const auth = createAuthStore();
export const isAdmin = derived(auth, ($auth) => $auth?.is_admin ?? false);
