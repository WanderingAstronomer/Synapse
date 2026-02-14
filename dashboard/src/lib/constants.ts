/** Category icons mapped by keyword pattern */
export const CATEGORY_ICONS: Record<string, string> = {};

/** All supported interaction types for multipliers */
export const INTERACTION_TYPES = [
	'MESSAGE',
	'REACTION_GIVEN',
	'REACTION_RECEIVED',
	'THREAD_CREATE',
	'VOICE_TICK',
	'IMAGE',
	'FILE',
	'LINK'
];

/** Rank medals for leaderboards */
export const RANK_MEDALS = ['#1', '#2', '#3', '#4', '#5'];

/** Achievement Rarity tiers (ordered) */
export const ACHIEVEMENT_RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];

/** Achievement Categories */
export const ACHIEVEMENT_CATEGORIES = ['social', 'coding', 'engagement', 'special'];

/** Activity chart day ranges */
export const ACTIVITY_DAY_OPTIONS = [7, 14, 30, 90];

/** Log levels for admin panel */
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

/** Flash message configuration */
export const FLASH_CONFIG: Record<string, { styles: string; icon: string }> = {
	success: { styles: 'bg-green-500/10 border-green-500/30 text-green-400', icon: '✓' },
	error:   { styles: 'bg-red-500/10 border-red-500/30 text-red-400', icon: '✕' },
	info:    { styles: 'bg-blue-500/10 border-blue-500/30 text-blue-400', icon: 'ℹ' },
	warning: { styles: 'bg-amber-500/10 border-amber-500/30 text-amber-400', icon: '⚠' },
};

/** Navigation Links */
export const NAV_LINKS = {
	public: [
		{ slug: 'dashboard', href: '/', label: 'Overview', icon: '' },
		{ slug: 'leaderboard', href: '/leaderboard', label: 'Leaderboard', icon: '' },
		{ slug: 'activity', href: '/activity', label: 'Activity', icon: '' },
		{ slug: 'achievements', href: '/achievements', label: 'Achievements', icon: '' },
	],
	admin: [
		{ href: '/admin/reward-rules', label: 'Reward Rules', icon: '' },
		{ href: '/admin/achievements', label: 'Achievements', icon: '' },
		{ href: '/admin/awards', label: 'Awards', icon: '' },
		{ href: '/admin/media', label: 'Media', icon: '' },
		{ href: '/admin/data-sources', label: 'Event Lake', icon: '' },
		{ href: '/admin/settings', label: 'Settings', icon: '' },
		{ href: '/admin/logs', label: 'Logs', icon: '' },
	]
};
