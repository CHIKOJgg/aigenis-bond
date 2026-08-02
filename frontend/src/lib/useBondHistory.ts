import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'aigenis_bond_history';
const MAX_ITEMS = 50;

export interface BondHistoryItem {
  internal_id: string;
  name: string;
  timestamp: number;
}

export function useBondHistory() {
  const [history, setHistory] = useState<BondHistoryItem[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch { /* quota exceeded */ }
  }, [history]);

  const addBond = useCallback((internal_id: string, name: string) => {
    setHistory((prev) => {
      const filtered = prev.filter((h) => h.internal_id !== internal_id);
      return [{ internal_id, name, timestamp: Date.now() }, ...filtered].slice(0, MAX_ITEMS);
    });
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  return { history, addBond, clearHistory };
}
