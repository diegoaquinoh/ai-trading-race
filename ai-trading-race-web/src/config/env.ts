/**
 * Environment helpers.
 *
 * `isDev`  — true during local development (`vite dev`)
 * `isProd` — true for production builds (`vite build`)
 *
 * Usage:
 *   import { isDev, isProd } from '../config/env';
 */
export const isDev: boolean = import.meta.env.DEV;
export const isProd: boolean = !isDev;
