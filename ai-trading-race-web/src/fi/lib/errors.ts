import axios from 'axios';
import { getErrorMessage, isNetworkError } from '../../services/errorUtils';

export function httpStatus(error: unknown): number | undefined {
    return axios.isAxiosError(error) ? error.response?.status : undefined;
}

export function isNotFound(error: unknown): boolean {
    return httpStatus(error) === 404;
}

export function isAuthError(error: unknown): boolean {
    const status = httpStatus(error);
    return status === 401 || status === 403;
}

interface ProblemBody {
    title?: string;
    detail?: string;
    code?: string;
    errors?: Record<string, string[]>;
}

/** Human-readable message using RFC 7807 problem details when the API returns them. */
export function describeError(error: unknown): string {
    if (isNetworkError(error)) return getErrorMessage(error);
    const status = httpStatus(error);
    if (status === 401) return 'Not signed in (401). This action needs an authenticated session.';
    if (status === 403) return 'Forbidden (403). Your role does not permit this action (operator or admin required).';
    if (axios.isAxiosError(error)) {
        const body = error.response?.data as ProblemBody | undefined;
        if (body && typeof body === 'object') {
            const parts = [body.title, body.detail].filter(Boolean);
            if (body.errors) {
                for (const [field, messages] of Object.entries(body.errors)) {
                    parts.push(`${field}: ${messages.join(' ')}`);
                }
            }
            if (parts.length > 0) return `${parts.join(' — ')}${status ? ` (${status})` : ''}`;
        }
        if (status === 429) return 'Rate or budget limit reached (429). Try again later.';
        if (status === 503) return 'A required dependency is unavailable (503).';
    }
    return getErrorMessage(error);
}
