/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			colors: {
				brand: {
					50: '#f3f0ff',
					100: '#e9e3ff',
					200: '#d5cbff',
					300: '#b7a4ff',
					400: '#9370ff',
					500: '#7c3aed',
					600: '#6d28d9',
					700: '#5b21b6',
					800: '#4c1d95',
					900: '#3b0764',
					950: '#1e0038',
				},
				gold: {
					300: '#fcd34d',
					400: '#fbbf24',
					500: '#f59e0b',
					600: '#d97706',
				},
				surface: {
					0: '#0a0a0f',
					50: '#0e0e14',
					100: '#13131a',
					200: '#1a1a24',
					300: '#26263a',
					400: '#3a3a52',
					500: '#52526b',
					600: '#71718a',
				},
				rarity: {
					common: '#9ca3af',
					uncommon: '#34d399',
					rare: '#60a5fa',
					epic: '#a78bfa',
					legendary: '#fbbf24',
				},
			},
			fontFamily: {
				sans: ['Inter', 'system-ui', 'sans-serif'],
				mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
			},
			animation: {
				'fade-in': 'fadeIn 0.3s ease-out',
				'slide-up': 'slideUp 0.4s ease-out',
				'glow': 'glow 2s ease-in-out infinite alternate',
				'glow-legendary': 'glowLegendary 2s ease-in-out infinite alternate',
				'glow-epic': 'glowEpic 2s ease-in-out infinite alternate',
				'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
				'gradient-shift': 'gradientShift 8s ease infinite',
				'float': 'float 6s ease-in-out infinite',
				'ticker': 'ticker 30s linear infinite',
			},
			keyframes: {
				fadeIn: {
					'0%': { opacity: '0' },
					'100%': { opacity: '1' },
				},
				slideUp: {
					'0%': { opacity: '0', transform: 'translateY(10px)' },
					'100%': { opacity: '1', transform: 'translateY(0)' },
				},
				glow: {
					'0%': { boxShadow: '0 0 5px rgba(124, 58, 237, 0.2)' },
					'100%': { boxShadow: '0 0 20px rgba(124, 58, 237, 0.4)' },
				},
				glowLegendary: {
					'0%': { boxShadow: '0 0 8px rgba(251, 191, 36, 0.15), inset 0 0 8px rgba(251, 191, 36, 0.05)' },
					'100%': { boxShadow: '0 0 24px rgba(251, 191, 36, 0.35), inset 0 0 16px rgba(251, 191, 36, 0.08)' },
				},
				glowEpic: {
					'0%': { boxShadow: '0 0 8px rgba(167, 139, 250, 0.15), inset 0 0 8px rgba(167, 139, 250, 0.05)' },
					'100%': { boxShadow: '0 0 24px rgba(167, 139, 250, 0.35), inset 0 0 16px rgba(167, 139, 250, 0.08)' },
				},
				gradientShift: {
					'0%, 100%': { backgroundPosition: '0% 50%' },
					'50%': { backgroundPosition: '100% 50%' },
				},
				float: {
					'0%, 100%': { transform: 'translateY(0)' },
					'50%': { transform: 'translateY(-6px)' },
				},
				ticker: {
					'0%': { transform: 'translateX(100%)' },
					'100%': { transform: 'translateX(-100%)' },
				},
			},
		},
	},
	plugins: [],
};
