import { useState } from 'react';
import type { ReactNode } from 'react';
import { describeError, isAuthError } from '../lib/errors';

interface OperatorActionProps {
    label: string;
    icon: string;
    /** Calls an admin endpoint; the server enforces Operator/Admin roles. */
    action: () => Promise<unknown>;
    confirmText?: string;
    disabled?: boolean;
    renderResult?: (result: unknown) => ReactNode;
}

/**
 * Button for an operator-only command. It never hides itself based on client-side
 * role guesses: the server decides, and 401/403 are explained instead of failing silently.
 */
export function OperatorAction({ label, icon, action, confirmText, disabled, renderResult }: OperatorActionProps) {
    const [state, setState] = useState<{ status: 'idle' | 'running' | 'done' | 'error'; result?: unknown; error?: unknown }>({ status: 'idle' });

    const run = async () => {
        if (confirmText && !window.confirm(confirmText)) return;
        setState({ status: 'running' });
        try {
            const result = await action();
            setState({ status: 'done', result });
        } catch (error) {
            setState({ status: 'error', error });
        }
    };

    return (
        <div className="fi-operator-action">
            <button className="fi-button" onClick={run} disabled={disabled || state.status === 'running'}>
                <i className={`fas ${state.status === 'running' ? 'fa-spinner fa-spin' : icon}`}></i> {label}
            </button>
            {state.status === 'error' && (
                <p className={`fi-inline-error ${isAuthError(state.error) ? 'fi-inline-auth' : ''}`} role="alert">
                    <i className={`fas ${isAuthError(state.error) ? 'fa-lock' : 'fa-exclamation-triangle'}`}></i> {describeError(state.error)}
                </p>
            )}
            {state.status === 'done' && (
                <div className="fi-operator-result">
                    <i className="fas fa-check"></i> Accepted.
                    {renderResult ? renderResult(state.result) : null}
                </div>
            )}
        </div>
    );
}
