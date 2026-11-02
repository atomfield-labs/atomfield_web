// Asked before the address leaves a page holding work that is not saved.
let askToLeave: (() => boolean) | null = null;

/**
 * Set what to ask before leaving; null when leaving would lose nothing.
 */
export function setLeaveGuard(ask: (() => boolean) | null): void {
  askToLeave = ask;
}

/**
 * Whether the address may leave this page.
 */
export function mayLeave(): boolean {
  return askToLeave ? askToLeave() : true;
}
