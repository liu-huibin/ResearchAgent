import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import type { Document } from '../types';

interface UploadState {
  id: string;
  filename: string;
  progress: number;
}

export function useKnowledgeBase() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const load = useCallback(async () => {
    try {
      const docs = await api.listKnowledge();
      setDocuments(docs);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upload = useCallback(async (file: File) => {
    const id = `${file.name}-${Date.now()}-${crypto.randomUUID()}`;
    setUploads(prev => [...prev, { id, filename: file.name, progress: 0 }]);

    try {
      await api.uploadKnowledge(file, (pct) => {
        setUploads(prev =>
          prev.map(u => u.id === id ? { ...u, progress: pct } : u)
        );
      });
      setUploads(prev => prev.filter(u => u.id !== id));
      await load();
    } catch (err) {
      setUploads(prev => prev.filter(u => u.id !== id));
      const message = err instanceof Error ? err.message : '上传失败';
      alert(message);
    }
  }, [load]);

  const remove = useCallback(async (docId: number) => {
    try {
      await api.deleteKnowledge(docId);
      setDocuments(prev => prev.filter(d => d.id !== docId));
    } catch {
      alert('删除失败');
    }
  }, []);

  return { documents, loading, uploads, upload, remove, reload: load };
}
