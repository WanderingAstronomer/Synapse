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
		...(options.headers as Record<string, string> || {}),
	};
	// Only set Content-Type for requests that carry a JSON body.
	// FormData requests (handled by uploadFormData) need the browser to set
	// the multipart boundary automatically, and bodyless requests (GET/DELETE)
	// don't need a content type at all.
	if (options.body && !(options.body instanceof FormData)) {
		headers['Content-Type'] ??= 'application/json';
	}
	if (token) {
		headers['Authorization'] = `Bearer ${token}`;
	}

	let res: Response;
	try {
		res = await fetch(`${BASE}${path}`, { ...options, headers });
	} catch (err) {
		console.error(`[api] Network error: ${options.method || 'GET'} ${path}`, err);
		throw new ApiError(0, `Network error: ${(err as Error).message}`);
	}

	if (!res.ok) {
		const body = await res.json().catch(() => ({ detail: res.statusText }));
		console.error(`[api] HTTP ${res.status}: ${options.method || 'GET'} ${path}`, body);

		// Global 401 handler: expired/invalid token — clear session and redirect.
		// Skip for the /auth/me endpoint itself to avoid loops during init().
		if (res.status === 401 && path !== '/auth/me') {
			// Lazy import to avoid circular dependency (auth → api → auth)
			import('$lib/stores/auth.svelte').then(({ auth }) => auth.expiredLogout());
		}

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

/**
 * Upload a file via multipart form-data.
 * Shared helper for badge, media, and generic uploads.
 */
async function uploadFormData<T = { url: string }>(path: string, file: File): Promise<T> {
	const formData = new FormData();
	formData.append('file', file);
	const token = getToken();
	const headers: Record<string, string> = {};
	if (token) headers['Authorization'] = `Bearer ${token}`;

	const res = await fetch(`${BASE}${path}`, {
		method: 'POST',
		headers,
		body: formData,
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
		throw new ApiError(res.status, err.detail || 'Upload failed');
	}
	return res.json();
}

// ---------------------------------------------------------------------------
// Public endpoints
// ---------------------------------------------------------------------------
export interface Metrics {
	total_users: number;
	total_xp: number;
	total_gold: number;
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
	category: string | null;
	rarity: string | null;
	rarity_color: string;
	xp_reward: number;
	gold_reward: number;
	badge_image: string | null;
	earner_count: number;
	earn_pct: number;
	series_id: number | null;
	series_order: number | null;
}

export interface RecentAchievement {
	user_id: string;
	user_name: string;
	avatar_url: string;
	achievement_name: string;
	achievement_rarity: string | null;
	rarity_color: string;
	earned_at: string | null;
}

export type PublicSettings = Record<string, unknown>;

export const api = {
	// Public
	getMetrics: () => request<Metrics>('/metrics'),
	getLeaderboard: (currency: string, page = 1, pageSize = 20) =>
		request<LeaderboardResponse>(`/leaderboard/${encodeURIComponent(currency)}?page=${page}&page_size=${pageSize}`),
	getActivity: (days = 30, limit = 100, eventType?: string) => {
		let url = `/activity?days=${days}&limit=${limit}`;
		if (eventType) url += `&event_type=${encodeURIComponent(eventType)}`;
		return request<ActivityResponse>(url);
	},
	getAchievements: () => request<{ achievements: Achievement[] }>('/achievements'),
	getRecentAchievements: (limit = 10) =>
		request<{ recent: RecentAchievement[] }>(`/achievements/recent?limit=${limit}`),
	getPublicSettings: () => request<PublicSettings>('/settings/public'),
	getLayout: (pageSlug: string) => request<PageLayout>(`/layouts/${encodeURIComponent(pageSlug)}`),
	getAllLayouts: () => request<PageLayout[]>('/layouts'),

	// Auth
	getMe: () => request<{ id: string; username: string; avatar: string | null; is_admin: boolean }>('/auth/me'),

	// Admin
	admin: {
		// Channel type defaults & overrides (reward rules)
		getChannelDefaults: () =>
			request<{ defaults: TypeDefault[] }>('/admin/channel-defaults'),
		upsertChannelDefault: (data: TypeDefaultUpsert) =>
			request<TypeDefault>('/admin/channel-defaults', { method: 'PUT', body: JSON.stringify(data) }),
		deleteChannelDefault: (id: number) =>
			request<void>(`/admin/channel-defaults/${id}`, { method: 'DELETE' }),
		getChannelOverrides: () =>
			request<{ overrides: ChannelOverrideRow[] }>('/admin/channel-overrides'),
		upsertChannelOverride: (data: ChannelOverrideUpsert) =>
			request<ChannelOverrideRow>('/admin/channel-overrides', { method: 'PUT', body: JSON.stringify(data) }),
		deleteChannelOverride: (id: number) =>
			request<void>(`/admin/channel-overrides/${id}`, { method: 'DELETE' }),

		// Channels
		getChannels: () => request<{ channels: DiscordChannel[] }>('/admin/channels'),
		syncChannels: () => request<{ synced: boolean; upserted: number; removed: number }>('/admin/channels/sync', { method: 'POST' }),

		getAchievements: () => request<{ achievements: AdminAchievement[] }>('/admin/achievements'),
		createAchievement: (data: AchievementCreatePayload) =>
			request<{ id: number; name: string }>('/admin/achievements', { method: 'POST', body: JSON.stringify(data) }),
		updateAchievement: (id: number, data: AchievementUpdatePayload) =>
			request<{ id: number; name: string; active: boolean }>(
				`/admin/achievements/${id}`, { method: 'PATCH', body: JSON.stringify(data) }
			),
		deleteAchievement: (id: number) =>
			request<void>(`/admin/achievements/${id}`, { method: 'DELETE' }),

		// Achievement categories
		getAchievementCategories: () =>
			request<{ categories: AchievementCategoryItem[] }>('/admin/achievement-categories'),
		createAchievementCategory: (data: { name: string; icon?: string; sort_order?: number }) =>
			request<{ id: number; name: string }>('/admin/achievement-categories', { method: 'POST', body: JSON.stringify(data) }),
		updateAchievementCategory: (id: number, data: Partial<{ name: string; icon: string; sort_order: number }>) =>
			request<{ id: number; name: string }>(`/admin/achievement-categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
		deleteAchievementCategory: (id: number) =>
			request<void>(`/admin/achievement-categories/${id}`, { method: 'DELETE' }),

		// Achievement rarities
		getAchievementRarities: () =>
			request<{ rarities: AchievementRarityItem[] }>('/admin/achievement-rarities'),
		createAchievementRarity: (data: { name: string; color?: string; emoji?: string; sort_order?: number }) =>
			request<{ id: number; name: string }>('/admin/achievement-rarities', { method: 'POST', body: JSON.stringify(data) }),
		updateAchievementRarity: (id: number, data: Partial<{ name: string; color: string; emoji: string; sort_order: number }>) =>
			request<{ id: number; name: string }>(`/admin/achievement-rarities/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
		deleteAchievementRarity: (id: number) =>
			request<void>(`/admin/achievement-rarities/${id}`, { method: 'DELETE' }),

		// Achievement series
		getAchievementSeries: () =>
			request<{ series: AchievementSeriesItem[] }>('/admin/achievement-series'),
		createAchievementSeries: (data: { name: string; description?: string }) =>
			request<{ id: number; name: string }>('/admin/achievement-series', { method: 'POST', body: JSON.stringify(data) }),
		updateAchievementSeries: (id: number, data: Partial<{ name: string; description: string }>) =>
			request<{ id: number; name: string }>(`/admin/achievement-series/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
		deleteAchievementSeries: (id: number) =>
			request<void>(`/admin/achievement-series/${id}`, { method: 'DELETE' }),

		// Trigger types — static client-side data (no backend call)
		getTriggerTypes: (): Promise<{ trigger_types: TriggerTypeInfo[] }> =>
			Promise.resolve({ trigger_types: TRIGGER_TYPES }),

		// Badge upload (uses unified media endpoint)
		uploadBadge: (file: File): Promise<{ url: string }> =>
			uploadFormData('/admin/media', file),

		// Media library
		getMedia: () =>
			request<{ files: MediaFileItem[] }>('/admin/media'),
		uploadMedia: (file: File): Promise<{ id: number; url: string; original_name: string }> =>
			uploadFormData('/admin/media', file),
		updateMedia: (id: number, data: { alt_text?: string | null }) =>
			request<{ id: number; alt_text: string | null }>(`/admin/media/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
		deleteMedia: (id: number) =>
			request<void>(`/admin/media/${id}`, { method: 'DELETE' }),

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

		// Setup / Bootstrap
		getSetupStatus: () =>
			request<SetupStatus>('/admin/setup/status'),
		runBootstrap: () =>
			request<BootstrapResult>('/admin/setup/bootstrap', { method: 'POST' }),

		// Live Logs
		getLogs: (params: { tail?: number; level?: string; logger?: string } = {}) => {
			const p = new URLSearchParams();
			if (params.tail) p.set('tail', String(params.tail));
			if (params.level) p.set('level', params.level);
			if (params.logger) p.set('logger', params.logger);
			return request<LogsResponse>(`/admin/logs?${p.toString()}`);
		},
		setLogLevel: (level: string) =>
			request<{ level: string }>('/admin/logs/level', {
				method: 'PUT',
				body: JSON.stringify({ level }),
			}),

		// Name resolution (user/channel IDs → display names)
		resolveNames: (userIds: string[] = [], channelIds: string[] = []) =>
			request<{ users: Record<string, string>; channels: Record<string, string> }>(
				'/admin/resolve-names',
				{ method: 'POST', body: JSON.stringify({ user_ids: userIds, channel_ids: channelIds }) }
			),

		// Layouts & Cards
		getLayout: (pageSlug: string) =>
			request<PageLayout>(`/layouts/${encodeURIComponent(pageSlug)}`),
		getAllLayouts: () =>
			request<PageLayout[]>('/layouts'),
		updateLayout: (pageSlug: string, data: LayoutUpdatePayload) =>
			request<PageLayout>(`/admin/layouts/${encodeURIComponent(pageSlug)}`, {
				method: 'PUT', body: JSON.stringify(data),
			}),
		createCard: (data: CardCreatePayload) =>
			request<CardConfig>('/admin/cards', {
				method: 'POST', body: JSON.stringify(data),
			}),
		updateCard: (cardId: string, data: CardUpdatePayload) =>
			request<CardConfig>(`/admin/cards/${encodeURIComponent(cardId)}`, {
				method: 'PATCH', body: JSON.stringify(data),
			}),
		deleteCard: (cardId: string) =>
			request<{ deleted: boolean }>(`/admin/cards/${encodeURIComponent(cardId)}`, { method: 'DELETE' }),

		// Uploads (uses unified media endpoint)
		uploadFile: (file: File): Promise<{ url: string }> =>
			uploadFormData('/admin/media', file),
	},
};

// ---------------------------------------------------------------------------
// Admin types — Reward Rules (Channel-First)
// ---------------------------------------------------------------------------
export interface TypeDefault {
	id: number;
	guild_id: string;
	channel_type: string;
	event_type: string;
	xp_multiplier: number;
	star_multiplier: number;
}

export interface TypeDefaultUpsert {
	channel_type: string;
	event_type: string;
	xp_multiplier: number;
	star_multiplier: number;
}

export interface ChannelOverrideRow {
	id: number;
	guild_id: string;
	channel_id: string;
	event_type: string;
	xp_multiplier: number;
	star_multiplier: number;
	reason: string | null;
}

export interface ChannelOverrideUpsert {
	channel_id: string;
	event_type: string;
	xp_multiplier: number;
	star_multiplier: number;
	reason?: string;
}

export interface ChannelRef {
	id: string;
	name: string | null;
	type: string | null;
}

export interface DiscordChannel {
	id: string;
	name: string;
	type: string;
	discord_category_id: string | null;
	discord_category_name: string | null;
	position: number;
}

export interface AdminAchievement {
	id: number;
	name: string;
	description: string | null;
	category_id: number | null;
	rarity_id: number | null;
	trigger_type: string;
	trigger_config: Record<string, unknown> | null;
	series_id: number | null;
	series_order: number | null;
	xp_reward: number;
	gold_reward: number;
	badge_image: string | null;
	announce_channel_id: string | null;
	is_hidden: boolean;
	max_earners: number | null;
	active: boolean;
	created_at: string | null;
}

export interface AchievementCreatePayload {
	name: string;
	description?: string;
	category_id?: number | null;
	rarity_id?: number | null;
	trigger_type: string;
	trigger_config?: Record<string, unknown>;
	series_id?: number | null;
	series_order?: number | null;
	xp_reward?: number;
	gold_reward?: number;
	badge_image?: string;
	announce_channel_id?: number;
	is_hidden?: boolean;
	max_earners?: number | null;
}

export interface AchievementUpdatePayload extends Partial<AchievementCreatePayload> {
	active?: boolean;
}

export interface AchievementCategoryItem {
	id: number;
	name: string;
	icon: string | null;
	sort_order: number;
}

export interface AchievementRarityItem {
	id: number;
	name: string;
	color: string;
	emoji: string | null;
	sort_order: number;
}

export interface AchievementSeriesItem {
	id: number;
	name: string;
	description: string | null;
}

export interface TriggerTypeInfo {
	value: string;
	label: string;
	description: string;
	config_schema: Record<string, unknown>;
}

/** Static trigger-type metadata (no backend call needed). */
const TRIGGER_TYPES: TriggerTypeInfo[] = [
	{ value: 'stat_threshold', label: 'Stat Threshold', description: 'Triggered when a stat reaches a threshold', config_schema: { stat: 'string', threshold: 'number' } },
	{ value: 'xp_milestone', label: 'XP Milestone', description: 'Triggered at an XP milestone', config_schema: { xp: 'number' } },
	{ value: 'star_milestone', label: 'Star Milestone', description: 'Triggered at a star milestone', config_schema: { stars: 'number' } },
	{ value: 'level_reached', label: 'Level Reached', description: 'Triggered when reaching a specific level', config_schema: { level: 'number' } },
	{ value: 'level_interval', label: 'Level Interval', description: 'Triggered every N levels', config_schema: { interval: 'number' } },
	{ value: 'event_count', label: 'Event Count', description: 'Triggered after N events of a type', config_schema: { event_type: 'string', count: 'number' } },
	{ value: 'first_event', label: 'First Event', description: 'Triggered on first event of a type', config_schema: { event_type: 'string' } },
	{ value: 'member_tenure', label: 'Member Tenure', description: 'Triggered after N days of membership', config_schema: { days: 'number' } },
	{ value: 'invite_count', label: 'Invite Count', description: 'Triggered after N invites', config_schema: { count: 'number' } },
	{ value: 'manual', label: 'Manual', description: 'Manually awarded by an admin', config_schema: {} },
];

export interface MediaFileItem {
	id: number;
	url: string;
	original_name: string;
	content_type: string | null;
	size_bytes: number;
	alt_text: string | null;
	uploaded_at: string | null;
}

export interface ManualAwardPayload {
	user_id: string;
	display_name?: string;
	xp?: number;
	gold?: number;
	reason?: string;
}

export interface GrantAchievementPayload {
	user_id: string;
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
	period: string;
	count: number;
}

export interface CounterListResponse {
	total: number;
	page: number;
	page_size: number;
	counters: CounterRow[];
}

// ---------------------------------------------------------------------------
// Setup / Bootstrap types
// ---------------------------------------------------------------------------
export interface GuildSnapshotInfo {
	guild_id: string;
	guild_name: string;
	channel_count: number;
	captured_at: string;
}

export interface SetupStatus {
	initialized: boolean;
	bootstrap_version: number | null;
	bootstrap_timestamp: string | null;
	has_guild_snapshot: boolean;
	guild_snapshot: GuildSnapshotInfo | null;
	has_channels: boolean;
}

export interface BootstrapResult {
	success: boolean;
	channels_synced: number;
	season_created: boolean;
	settings_written: number;
	warnings: string[];
}

// ---------------------------------------------------------------------------
// Live Logs types
// ---------------------------------------------------------------------------
export interface LogEntry {
	timestamp: string;
	level: string;
	logger: string;
	message: string;
}

export interface LogsResponse {
	entries: LogEntry[];
	total: number;
	capture_level: string;
	valid_levels: string[];
}

// ---------------------------------------------------------------------------
// Layout, Card & Brand types
// ---------------------------------------------------------------------------
export interface CardConfig {
	id: string;
	page_layout_id: string;
	card_type: string;
	position: number;
	grid_span: number;
	title: string | null;
	subtitle: string | null;
	config_json: Record<string, unknown> | null;
	visible: boolean;
}

export interface PageLayout {
	id: string;
	guild_id: number;
	page_slug: string;
	display_name: string;
	layout_json: Record<string, unknown> | null;
	updated_by: number | null;
	updated_at: string | null;
	cards: CardConfig[];
}

export interface LayoutUpdatePayload {
	display_name?: string;
	layout_json?: Record<string, unknown>;
	card_order?: string[];
}

export interface CardCreatePayload {
	page_layout_id: string;
	card_type: string;
	position?: number;
	grid_span?: number;
	title?: string;
	subtitle?: string;
	config_json?: Record<string, unknown>;
}

export interface CardUpdatePayload {
	card_type?: string;
	position?: number;
	grid_span?: number;
	title?: string;
	subtitle?: string;
	config_json?: Record<string, unknown>;
	visible?: boolean;
}
