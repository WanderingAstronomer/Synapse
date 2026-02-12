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

		// Event Lake (P4)
		getEventLakeEvents: (params: EventLakeQuery = {}) => {
			const p = new URLSearchParams();
			if (params.page) p.set('page', String(params.page));
			if (params.page_size) p.set('page_size', String(params.page_size));
			if (params.event_type) p.set('event_type', params.event_type);
			if (params.user_id) p.set('user_id', String(params.user_id));
			if (params.channel_id) p.set('channel_id', String(params.channel_id));
			if (params.since) p.set('since', params.since);
			if (params.until) p.set('until', params.until);
			return request<EventLakeListResponse>(`/admin/event-lake/events?${p.toString()}`);
		},
		getDataSources: () =>
			request<DataSourceConfig[]>('/admin/event-lake/data-sources'),
		toggleDataSources: (toggles: DataSourceToggle[]) =>
			request<{ updated: number }>('/admin/event-lake/data-sources', {
				method: 'PUT', body: JSON.stringify(toggles),
			}),
		getEventLakeHealth: (days = 30) =>
			request<EventLakeHealth>(`/admin/event-lake/health?days=${days}`),
		getStorageEstimate: () =>
			request<StorageEstimate>('/admin/event-lake/storage-estimate'),
		triggerRetention: (days = 90) =>
			request<RetentionResult>(`/admin/event-lake/retention/run?retention_days=${days}`, { method: 'POST' }),
		triggerReconciliation: () =>
			request<ReconciliationResult>('/admin/event-lake/reconciliation/run', { method: 'POST' }),
		triggerBackfill: (dryRun = false) =>
			request<BackfillResult>(`/admin/event-lake/backfill/run?dry_run=${dryRun}`, { method: 'POST' }),
		getCounters: (params: CounterQuery = {}) => {
			const p = new URLSearchParams();
			if (params.user_id) p.set('user_id', String(params.user_id));
			if (params.event_type) p.set('event_type', params.event_type);
			if (params.period) p.set('period', params.period);
			if (params.page) p.set('page', String(params.page));
			if (params.page_size) p.set('page_size', String(params.page_size));
			return request<CounterListResponse>(`/admin/event-lake/counters?${p.toString()}`);
		},
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

// ---------------------------------------------------------------------------
// Event Lake types (P4)
// ---------------------------------------------------------------------------
export interface EventLakeRow {
	id: number;
	guild_id: string;
	user_id: string;
	event_type: string;
	channel_id: string | null;
	target_id: string | null;
	payload: Record<string, unknown>;
	source_id: string | null;
	timestamp: string;
}

export interface EventLakeListResponse {
	total: number;
	page: number;
	page_size: number;
	events: EventLakeRow[];
}

export interface EventLakeQuery {
	page?: number;
	page_size?: number;
	event_type?: string;
	user_id?: number;
	channel_id?: number;
	since?: string;
	until?: string;
}

export interface DataSourceConfig {
	event_type: string;
	enabled: boolean;
	label: string;
	description: string;
}

export interface DataSourceToggle {
	event_type: string;
	enabled: boolean;
}

export interface VolumePoint {
	date: string;
	event_type: string;
	count: number;
}

export interface EventLakeHealth {
	total_events: number;
	total_counters: number;
	oldest_event: string | null;
	newest_event: string | null;
	table_size_bytes: number;
	events_today: number;
	events_7d: number;
	volume_by_type: Record<string, number>;
	daily_volume: VolumePoint[];
}

export interface StorageEstimate {
	avg_row_bytes: number;
	total_rows: number;
	estimated_bytes: number;
	estimated_mb: number;
	estimated_gb: number;
	daily_rate: number;
	days_of_data: number;
	projected_90d_mb: number;
}

export interface RetentionResult {
	events_deleted: number;
	counters_deleted: number;
}

export interface ReconciliationResult {
	checked: number;
	corrected: number;
	corrections: Array<Record<string, unknown>>;
	timestamp: string;
}

export interface BackfillResult {
	rows_read: number;
	counters_upserted: number;
	skipped_types: string[];
	dry_run: boolean;
	timestamp: string;
}

export interface CounterQuery {
	user_id?: number;
	event_type?: string;
	period?: string;
	page?: number;
	page_size?: number;
}

export interface CounterRow {
	user_id: string;
	event_type: string;
	zone_id: number;
	period: string;
	count: number;
}

export interface CounterListResponse {
	total: number;
	page: number;
	page_size: number;
	counters: CounterRow[];
}
