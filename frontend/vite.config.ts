/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    test: {
        environment: 'node',
        include: ['src/**/*.{test,spec}.{ts,tsx}'],
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: process.env.VITE_API_TARGET || 'http://localhost:8000',
                changeOrigin: true,
                ws: true,
            },
        },
    },
    build: {
        rollupOptions: {
            output: {
                // Only group the React core (shared by eager + every lazy route).
                // Everything else (recharts, framer-motion, radix, react-query…) is
                // left to Rollup's automatic splitting so libs used only inside a
                // lazy route stay in that route's async chunk instead of being
                // pulled into the initial modulepreload graph.
                manualChunks(id) {
                    if (id.includes('node_modules')) {
                        if (
                            id.includes('/react/') ||
                            id.includes('/react-dom/') ||
                            id.includes('/react-router') ||
                            id.includes('/react-router-dom/') ||
                            id.includes('/scheduler/')
                        ) {
                            return 'react-vendor';
                        }
                    }
                },
            },
        },
    },
});
