import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'aigenis_watchlist_groups';

export interface WatchlistGroup {
  id: string;
  name: string;
  bondIds: string[];
}

export function useWatchlistGroups() {
  const [groups, setGroups] = useState<WatchlistGroup[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(groups)); }
    catch { /* quota exceeded */ }
  }, [groups]);

  const addGroup = useCallback((name: string) => {
    const id = crypto.randomUUID?.() || Date.now().toString(36);
    setGroups((prev) => [...prev, { id, name, bondIds: [] }]);
  }, []);

  const removeGroup = useCallback((id: string) => {
    setGroups((prev) => prev.filter((g) => g.id !== id));
  }, []);

  const renameGroup = useCallback((id: string, name: string) => {
    setGroups((prev) => prev.map((g) => g.id === id ? { ...g, name } : g));
  }, []);

  const addBondToGroup = useCallback((groupId: string, bondId: string) => {
    setGroups((prev) => prev.map((g) =>
      g.id === groupId && !g.bondIds.includes(bondId)
        ? { ...g, bondIds: [...g.bondIds, bondId] }
        : g
    ));
  }, []);

  const removeBondFromGroup = useCallback((groupId: string, bondId: string) => {
    setGroups((prev) => prev.map((g) =>
      g.id === groupId ? { ...g, bondIds: g.bondIds.filter((id) => id !== bondId) } : g
    ));
  }, []);

  return { groups, addGroup, removeGroup, renameGroup, addBondToGroup, removeBondFromGroup };
}
