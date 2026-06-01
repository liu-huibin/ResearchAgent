import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { DocumentTab } from '../types';

interface DocumentTabsContextType {
  tabs: DocumentTab[];
  activeTabId: string | null;
  openTab: (tab: Omit<DocumentTab, 'id'> & { id?: string }) => string;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  closeAllTabs: () => void;
}

const DocumentTabsContext = createContext<DocumentTabsContextType | null>(null);

export function DocumentTabsProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<DocumentTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  const openTab = useCallback(
    (tab: Omit<DocumentTab, 'id'> & { id?: string }): string => {
      const tabId = tab.id || `doc_${tab.documentId}`;
      setTabs((prev) => {
        const existing = prev.find((t) => t.id === tabId);
        if (existing) {
          return prev;
        }
        return [...prev, { ...tab, id: tabId }];
      });
      setActiveTabId(tabId);
      return tabId;
    },
    []
  );

  const closeTab = useCallback(
    (tabId: string) => {
      setTabs((prev) => {
        const idx = prev.findIndex((t) => t.id === tabId);
        const next = prev.filter((t) => t.id !== tabId);
        if (activeTabId === tabId && next.length > 0) {
          const newIdx = Math.min(idx, next.length - 1);
          setActiveTabId(next[newIdx].id);
        } else if (next.length === 0) {
          setActiveTabId(null);
        }
        return next;
      });
    },
    [activeTabId]
  );

  const setActiveTab = useCallback((tabId: string) => {
    setActiveTabId(tabId);
  }, []);

  const closeAllTabs = useCallback(() => {
    setTabs([]);
    setActiveTabId(null);
  }, []);

  return (
    <DocumentTabsContext.Provider
      value={{ tabs, activeTabId, openTab, closeTab, setActiveTab, closeAllTabs }}
    >
      {children}
    </DocumentTabsContext.Provider>
  );
}

export function useDocumentTabs(): DocumentTabsContextType {
  const ctx = useContext(DocumentTabsContext);
  if (!ctx) {
    throw new Error('useDocumentTabs must be used within DocumentTabsProvider');
  }
  return ctx;
}
