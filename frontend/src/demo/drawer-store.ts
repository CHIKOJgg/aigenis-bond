import { useSyncExternalStore } from 'react';

let currentBondId: string | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const fn of listeners) fn();
}

export const bondDrawerStore = {
  open(internalId: string) {
    if (currentBondId === internalId) return;
    currentBondId = internalId;
    emit();
  },
  close() {
    if (currentBondId === null) return;
    currentBondId = null;
    emit();
  },
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
  getSnapshot() {
    return currentBondId;
  },
};

export function useOpenBond(): string | null {
  return useSyncExternalStore(
    bondDrawerStore.subscribe,
    bondDrawerStore.getSnapshot,
  );
}