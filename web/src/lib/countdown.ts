/** Seconds left on a deadline that was `deadlineIn` seconds away when received at `receivedAt` (ms). */
export function remaining(deadlineIn: number | null, receivedAt: number, now: number): number | null {
  if (deadlineIn == null) return null;
  return Math.max(0, deadlineIn - (now - receivedAt) / 1000);
}

export function backoffMs(attempt: number): number {
  return Math.min(10_000, 500 * 2 ** attempt);
}
