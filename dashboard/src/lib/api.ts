/**
 * Typed API client for the Synapse FastAPI backend.
 * In dev, Vite proxies /api → localhost:8000.
 * In production, the SvelteKit container talks to the api service.
 */

const BASE = '/api';

function getToken(): string | null {
	if (typeof localStorage === 'undefined') return null;
	return localStorage.getItem('synapse_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
	const token = getToken();
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(options.headers as Record<string, string> || {}),
	};
	if (token) {
		headers['Authorization'] = `Bearer ${token}`;
	}

	const res = await fetch(`${BASE}${path}`, { ...options, headers });

	if (!res.ok) {
		const body = await res.json().catch(() => ({ detail: res.statusText }));
		throw new ApiError(res.status, body.detail || res.statusText);
	}

	return res.json();
}

export class ApiError extends Error {
	constructor(public status: number, message: string) {
		super(message);
		this.name = 'ApiError';
	}
}

// ---------------------------------------------------------------------------
// Public endpoints
// ---------------------------------------------------------------------------
export interface Metrics {
	total_users: number;
	total_xp: number;
	active_users_7d: number;
	top_level: number;
	total_achievements_earned: number;
}

export interface LeaderboardUser {
	id: string;
	discord_name: string;
	avatar_url: string;
	xp: number;
	level: number;
	gold: number;
	xp_for_next: number;
	xp_progress: number;
	rank: number;
	created_at: string | null;
}

export interface LeaderboardResponse {
	total: number;
	page: number;
	page_size: number;
	users: LeaderboardUser[];
}

export interface ActivityEvent {
	id: number;
	user_id: string;
	user_name: string;
	avatar_url: string;
	event_type: string;
	xp_delta: number;
	star_delta: number;
	timestamp: string | null;
	metadata: Record<string, unknown> | null;
}

export interface ActivityResponse {
	events: ActivityEvent[];
	daily: Record<string, Record<string, number>>;
}

export interface Achievement {
	id: number;
	name: string;
	description: string | null;
	category: string;
	rarity: string;
	rarity_label: string;
	rarity_color: string;
	xp_reward: number;
	gold_reward: number;
	badge_image_url: string | null;
	earner_count: number;
	earn_pct: number;
}

export interface RecentAchievement {
	user_id: string;
	user_name: string;
	avatar_url: string;
	achievement_name: string;
	achievement_rarity: string;
	rarity_color: string;
	earned_at: string | null;
}

export type PublicSettings = Record<string, unknown>;

export const api = {
	// Public
	getMetrics: () => request<Metrics>('/metrics'),
	getLeaderboard: (currency: string, page = 1, pageSize = 20) =>
		request<LeaderboardResponse>(`/leaderboard/${currency}?page=${page}&page_size=${pageSize}`),
	getActivity: (days = 30, limit = 100, eventType?: string) => {
		let url = `/activity?days=${days}&limit=${limit}`;
		if (eventType) url += `&event_type=${eventType}`;
		return request<ActivityResponse>(url);
	},
	getAchievements: () => request<{ achievements: Achievement[] }>('/achievements'),
	getRecentAchievements: (limit = 10) =>
		request<{ recent: RecentAchievement[] }>(`/achievements/recent?limit=${limit}`),
	getPublicSettings: () => request<PublicSettings>('/settings/public'),

	// Auth
	getMe: () => request<{ id: string; username: string; avatar: string | null; is_admin: boolean }>('/auth/me'),

	// Admin
	admin: {
		getZones: () => request<{ zones: AdminZone[] }>('/admin/zones'),
		createZone: (data: ZoneCreatePayload) =>
			request<{ id: number; name: string }>('/admin/zones', { method: 'POST', body: JSON.stringify(data) }),
		updateZone: (id: number, data: ZoneUpdatePayload) =>
			request<{ id: number; name: string; active: boolean }>(
				`/admin/zones/${id}`, { method: 'PATCH', body: JSON.stringify(data) }
			),

		getAchievements: () => request<{ achievements: AdminAchievement[] }>('/admin/achievements'),
		createAchievement: (data: AchievementCreatePayload) =>
			request<{ id: number; name: string }>('/admin/achievements', { method: 'POST', body: JSON.stringify(data) }),
		updateAchievement: (id: number, data: AchievementUpdatePayload) =>
			request<{ id: number; name: string; active: boolean }>(
				`/admin/achievements/${id}`, { method: 'PATCH', body: JSON.stringify(data) }
			),

		awardXpGold: (data: ManualAwardPayload) =>
			request<{ user_id: string; xp: number; gold: number; level: number }>(
				'/admin/awards/xp-gold', { method: 'POST', body: JSON.stringify(data) }
			),
		grantAchievement: (data: GrantAchievementPayload) =>
			request<{ message: string }>(
				'/admin/awards/achievement', { method: 'POST', body: JSON.stringify(data) }
			),

		searchUsers: (q = '', limit = 20) =>
			request<{ users: AdminUser[] }>(`/admin/users?q=${encodeURIComponent(q)}&limit=${limit}`),

		getSettings: () => request<{ settings: AdminSetting[] }>('/admin/settings'),
		updateSettings: (settings: SettingUpdatePayload[]) =>
			request<{ updated: number }>('/admin/settings', { method: 'PUT', body: JSON.stringify(settings) }),

		getAuditLog: (page = 1, pageSize = 25) =>
			request<AuditLogResponse>(`/admin/audit?page=${page}&page_size=${pageSize}`),
	},
};

// ---------------------------------------------------------------------------
// Admin types
// ---------------------------------------------------------------------------
export interface AdminZone {
	id: number;
	guild_id: string;
	name: string;
	description: string | null;
	active: boolean;
	created_by: string | null;
	created_at: string | null;
	channel_ids: string[];
	multipliers: Record<string, { xp: number; star: number }>;
}

export interface ZoneCreatePayload {
	name: string;
	description?: string;
	channel_ids?: number[];
	multipliers?: Record<string, number[]>;
}

export interface ZoneUpdatePayload {
	name?: string;
	description?: string;
	active?: boolean;
	channel_ids?: number[];
	multipliers?: Record<string, number[]>;
}

export interface AdminAchievement {
	id: number;
	name: string;
	description: string | null;
	category: string;
	requirement_type: string;
	requirement_scope: string;
	requirement_field: string | null;
	requirement_value: number | null;
	xp_reward: number;
	gold_reward: number;
	badge_image_url: string | null;
	rarity: string;
	announce_channel_id: string | null;
	active: boolean;
	created_at: string | null;
}

export interface AchievementCreatePayload {
	name: string;
	description?: string;
	category?: string;
	requirement_type?: string;
	requirement_scope?: string;
	requirement_field?: string;
	requirement_value?: number;
	xp_reward?: number;
	gold_reward?: number;
	badge_image_url?: string;
	rarity?: string;
	announce_channel_id?: number;
}

export interface AchievementUpdatePayload extends Partial<AchievementCreatePayload> {
	active?: boolean;
}

export interface ManualAwardPayload {
	user_id: number;
	display_name?: string;
	xp?: number;
	gold?: number;
	reason?: string;
}

export interface GrantAchievementPayload {
	user_id: number;
	display_name?: string;
	achievement_id: number;
}

export interface AdminUser {
	id: string;
	discord_name: string;
	level: number;
	xp: number;
}

export interface AdminSetting {
	key: string;
	value: unknown;
	category: string;
	description: string | null;
	updated_at: string | null;
}

export interface SettingUpdatePayload {
	key: string;
	value: unknown;
	category?: string;
	description?: string;
}

export interface AuditLogEntry {
	id: number;
	actor_id: string;
	action_type: string;
	target_table: string;
	target_id: string | null;
	before_snapshot: Record<string, unknown> | null;
	after_snapshot: Record<string, unknown> | null;
	reason: string | null;
	timestamp: string | null;
}

export interface AuditLogResponse {
	total: number;
	page: number;
	page_size: number;
	entries: AuditLogEntry[];
}
