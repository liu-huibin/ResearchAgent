import Layout from './components/Layout';
import Sidebar from './components/sidebar/Sidebar';
import DocumentViewer from './components/reader/DocumentViewer';
import ChatPanel from './components/chat/ChatPanel';
import { useSessions } from './hooks/useSessions';
import { useKnowledgeBase } from './hooks/useKnowledgeBase';

function App() {
  const { sessions, activeId, setActiveId, loading, create, commitPending, remove, rename, reload } = useSessions();
  const kb = useKnowledgeBase();

  return (
    <Layout
      sidebar={
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          loading={loading}
          onSelect={setActiveId}
          onCreate={create}
          onDelete={remove}
          onRename={rename}
          knowledgeDocs={kb.documents}
          knowledgeUploads={kb.uploads}
          knowledgeLoading={kb.loading}
          onKnowledgeUpload={kb.upload}
          onKnowledgeDelete={kb.remove}
        />
      }
      reader={<DocumentViewer sessionId={activeId} onCommitPending={commitPending} />}
      chat={<ChatPanel sessionId={activeId} onSessionUpdate={reload} onCommitPending={commitPending} />}
    />
  );
}

export default App;
