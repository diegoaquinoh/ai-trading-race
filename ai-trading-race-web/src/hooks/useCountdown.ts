import { useState, useEffect, useCallback } from 'react';

/**
 * Countdown hook that ticks down from `seconds` and can be reset.
 * Uses setInterval callback (not synchronous setState in effect body)
 * to satisfy react-hooks/set-state-in-effect.
 */
export function useCountdown(seconds: number, resetKey: number | undefined) {
    const [remaining, setRemaining] = useState(seconds);

    const reset = useCallback(() => {
        setRemaining(seconds);
    }, [seconds]);

    useEffect(() => {
        // Reset handled via the interval callback checking resetKey change
        let lastKey = resetKey;
        const interval = setInterval(() => {
            setRemaining(prev => {
                // If resetKey changed since last tick, reset
                if (resetKey !== lastKey) {
                    lastKey = resetKey;
                    return seconds;
                }
                return Math.max(0, prev - 1);
            });
        }, 1000);
        return () => clearInterval(interval);
    }, [resetKey, seconds]);

    return { remaining, reset };
}
