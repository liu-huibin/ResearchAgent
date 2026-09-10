import { useEffect, useRef } from 'react';
import { api } from '../services/api';
import { useDocumentTabs } from '../contexts/DocumentTabsContext';

let navigationKey = 0;

export function useCitation() {
  const { openTab } = useDocumentTabs();
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);
  return async (docId: number, chunkIndex: number) => {
    const version = ++request.current;
    try {
      const citation = await api.getCitation(docId, chunkIndex);
      if (version !== request.current) return;
      openTab({ documentId: docId, filename: citation.filename,
        fileUrl: api.getDocumentFileUrl(docId), isPdf: citation.file_type === 'pdf',
        label: citation.filename, citation, navigationKey: ++navigationKey });
    } catch (error) {
      if (version === request.current) {
        alert(error instanceof Error ? `引用定位失败：${error.message}` : '引用定位失败');
      }
    }
  };
}
