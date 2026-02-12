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
					0: '#09090b',
					50: '#0c0c0f',
					100: '#111116',
					200: '#18181b',
					300: '#27272a',
					400: '#3f3f46',
					500: '#52525b',
					600: '#71717a',
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
			},
		},
	},
	plugins: [],
};
