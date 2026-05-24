import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import type { Session } from '../types';

// Temp negative ID for pending sessions not yet created on backend
function makeTempId(): number {
  return -Date.now();
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const list = await api.listSessions();
      setSessions(list);
      if (!activeId && list.length > 0) {
        setActiveId(list[0].id);
      }
    } catch (err) {
      console.error('加载会话列表失败:', err);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    load();
  }, []);

  const create = useCallback(() => {
    const tempId = makeTempId();
    const pending: Session = {
      id: tempId,
      title: '新会话',
      active_document_id: null,
      updated_at: new Date().toISOString(),
    };
    setSessions((prev) => [pending, ...prev]);
    setActiveId(tempId);
    return pending;
  }, []);

  /** Commit a pending session to the backend, returns the real session */
  const commitPending = useCallback(async (tempId: number): Promise<Session | undefined> => {
    try {
      const real = await api.createSession();
      setSessions((prev) =>
        prev.map((s) => (s.id === tempId ? real : s))
      );
      setActiveId(real.id);
      return real;
    } catch (err) {
      console.error('创建会话失败:', err);
    }
  }, []);

  const remove = useCallback(async (id: number) => {
    // If it's a pending session, just remove it locally
    if (id < 0) {
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeId === id) {
        setActiveId(null);
      }
      return;
    }
    try {
      await api.deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeId === id) {
        setActiveId(null);
      }
    } catch (err) {
      console.error('删除会话失败:', err);
    }
  }, [activeId]);

  const rename = useCallback(async (id: number, title: string) => {
    // Pending sessions: just update local title
    if (id < 0) {
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, title } : s))
      );
      return;
    }
    try {
      const updated = await api.renameSession(id, title);
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, title: updated.title } : s))
      );
    } catch (err) {
      console.error('重命名失败:', err);
    }
  }, []);

  /** Switch active session, cleaning up empty pending sessions */
  const switchSession = useCallback((id: number | null) => {
    setSessions((prev) => {
      // If currently active session is pending and has no messages, remove it
      if (activeId && activeId < 0 && activeId !== id) {
        return prev.filter((s) => s.id !== activeId);
      }
      return prev;
    });
    setActiveId(id);
  }, [activeId]);

  return {
    sessions, activeId, setActiveId: switchSession, loading,
    create, commitPending, remove, rename, reload: load,
  };
}
