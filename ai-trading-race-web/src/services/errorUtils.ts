import axios from 'axios';

/**
 * Detects if an error is a network-level failure (server unreachable, CORS preflight failed, etc.)
 */
export function isNetworkError(error: unknown): boolean {
    if (!axios.isAxiosError(error)) return false;

    // No response at all → server didn't answer
    if (!error.response) return true;

    // Axios sets code = 'ERR_NETWORK' for genuine connection failures
    if (error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED') return true;

    return false;
}

/**
 * Returns a user-friendly error message.
 */
export function getErrorMessage(error: unknown): string {
    if (isNetworkError(error)) {
        return 'Server temporarily unavailable. Please try again later.';
    }

    if (axios.isAxiosError(error)) {
        const status = error.response?.status;
        if (status === 404) return 'Resource not found';
        if (status === 500) return 'Internal server error';
        if (status) return `Server error (${status})`;
    }

    if (error instanceof Error) return error.message;
    return 'An unexpected error occurred';
}
