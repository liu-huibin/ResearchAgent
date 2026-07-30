-- ResearchMate Database Initialization
-- Safe for both a fresh database and repeated execution.

CREATE DATABASE IF NOT EXISTS research_mate
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE research_mate;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL DEFAULT 'default_user',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO users (id, username) VALUES (1, 'default_user')
    ON DUPLICATE KEY UPDATE username = 'default_user';

-- documents is created first so sessions may safely reference it. The reverse
-- documents.session_id FK is added after both tables exist.
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL DEFAULT 1,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_md5 VARCHAR(32) NOT NULL,
    type VARCHAR(10) NOT NULL DEFAULT 'session',
    session_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_documents_user_id (user_id),
    INDEX idx_documents_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL DEFAULT 1,
    title VARCHAR(100) NOT NULL DEFAULT '新会话',
    active_document_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sessions_user_id (user_id),
    INDEX idx_sessions_active_document_id (active_document_id),
    CONSTRAINT fk_sessions_active_document
        FOREIGN KEY (active_document_id) REFERENCES documents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT,
    thought TEXT,
    tool_calls JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_messages_session_id (session_id),
    CONSTRAINT fk_messages_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    assistant_message_id INT NULL,
    trace_id VARCHAR(36) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'completed',
    prompt_variant VARCHAR(80) NOT NULL DEFAULT 'phase4-v1',
    prompt_version VARCHAR(80) NOT NULL DEFAULT '',
    langsmith_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    agent_usage JSON,
    iterations INT NOT NULL DEFAULT 0,
    tool_calls INT NOT NULL DEFAULT 0,
    tool_failures INT NOT NULL DEFAULT 0,
    duration_ms INT NOT NULL DEFAULT 0,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uq_workflow_runs_trace_id (trace_id),
    INDEX idx_workflow_runs_session_id (session_id),
    INDEX idx_workflow_runs_assistant_message_id (assistant_message_id),
    CONSTRAINT fk_workflow_runs_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- MySQL has no portable ADD CONSTRAINT IF NOT EXISTS. Query the schema first
-- so rerunning this script cannot create a duplicate circular FK.
SET @documents_session_fk_exists = (
    SELECT COUNT(*)
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'documents'
      AND COLUMN_NAME = 'session_id'
      AND REFERENCED_TABLE_NAME = 'sessions'
      AND REFERENCED_COLUMN_NAME = 'id'
);

SET @documents_session_fk_sql = IF(
    @documents_session_fk_exists = 0,
    'ALTER TABLE documents ADD CONSTRAINT fk_documents_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL',
    'SELECT 1'
);

PREPARE documents_session_fk_statement FROM @documents_session_fk_sql;
EXECUTE documents_session_fk_statement;
DEALLOCATE PREPARE documents_session_fk_statement;
