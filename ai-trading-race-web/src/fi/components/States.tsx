import type { ReactNode } from 'react';
import { EmptyState, ErrorMessage, LoadingSpinner } from '../../components/common';
import { describeError, isAuthError, isNotFound } from '../lib/errors';

interface QueryLike<T> {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
    data: T | undefined;
    refetch: () => unknown;
}

interface QueryStateProps<T> {
    query: QueryLike<T>;
    /** What is being loaded, e.g. "runs". */
    label: string;
    isEmpty?: (data: T) => boolean;
    emptyTitle?: string;
    emptyMessage?: string;
    /** Shown instead of a generic error for 404 (e.g. endpoint not yet deployed). */
    notFoundMessage?: string;
    compact?: boolean;
    children: (data: T) => ReactNode;
}

/** Loading, error, not-found and empty states for every query. */
export function QueryState<T>({
    query,
    label,
    isEmpty,
    emptyTitle,
    emptyMessage,
    notFoundMessage,
    compact = false,
    children,
}: QueryStateProps<T>) {
    if (query.isLoading) {
        return (
            <div className={compact ? 'fi-state-compact' : 'fi-state'}>
                <LoadingSpinner size={compact ? 'sm' : 'md'} message={`Loading ${label}…`} />
            </div>
        );
    }

    if (query.isError) {
        if (isNotFound(query.error) && notFoundMessage) {
            return compact
                ? <p className="fi-muted-note"><i className="fas fa-info-circle"></i> {notFoundMessage}</p>
                : <EmptyState icon="fa-search" title="Not available" message={notFoundMessage} />;
        }
        if (compact) {
            return (
                <p className="fi-inline-error" role="alert">
                    <i className="fas fa-exclamation-triangle"></i> Could not load {label}: {describeError(query.error)}{' '}
                    <button className="fi-link-button" onClick={() => query.refetch()}>Retry</button>
                </p>
            );
        }
        return (
            <ErrorMessage
                title={isAuthError(query.error) ? 'Access denied' : `Could not load ${label}`}
                message={describeError(query.error)}
                retryAction={() => query.refetch()}
            />
        );
    }

    if (query.data === undefined || (isEmpty && isEmpty(query.data))) {
        return compact
            ? <p className="fi-muted-note">{emptyMessage ?? `No ${label}.`}</p>
            : <EmptyState title={emptyTitle ?? `No ${label}`} message={emptyMessage ?? `There are no ${label} to show yet.`} />;
    }

    return <>{children(query.data)}</>;
}

export function InlineError({ error }: { error: unknown }) {
    if (!error) return null;
    return (
        <p className={`fi-inline-error ${isAuthError(error) ? 'fi-inline-auth' : ''}`} role="alert">
            <i className={`fas ${isAuthError(error) ? 'fa-lock' : 'fa-exclamation-triangle'}`}></i> {describeError(error)}
        </p>
    );
}
