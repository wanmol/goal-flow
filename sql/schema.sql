-- =====================================================================
-- goalflow — MySQL schema
-- =====================================================================
-- Business tables backing the durable stores in src/goalflow/model/:
--   * agent_message        -> Message                       (wf_message.py)
--   * agent_conv_variable  -> WorkflowConversationVariables (wf_conv_variable.py)
--   * agent_hitl_review    -> HITLReview                    (wf_hitl_review.py)
--
-- The LangGraph checkpointer tables (checkpoints, checkpoint_blobs,
-- checkpoint_writes, ...) are NOT created here — they are provisioned
-- automatically by PyMySQLSaver.setup() from langgraph-checkpoint-mysql
-- (see src/goalflow/infra/checkpointer_manager.py).
--
-- Target: MySQL 8.0+. Adjust the database name to match MYSQL_DB (env).
-- =====================================================================

-- CREATE DATABASE IF NOT EXISTS `aira`
--   DEFAULT CHARACTER SET utf8mb4
--   DEFAULT COLLATE utf8mb4_unicode_ci;
-- USE `aira`;

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- agent_message — one row per conversation turn (query + answer)
-- Model: src/goalflow/model/wf_message.py::Message
-- Note: the ORM attributes created_at / updated_at map to the physical
--       columns `create_time` / `last_update_time` respectively.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `agent_message` (
    `id`               BIGINT       NOT NULL AUTO_INCREMENT,
    `conversation_id`  VARCHAR(36)  NOT NULL                COMMENT 'session id',
    `message_id`       VARCHAR(36)  NOT NULL                COMMENT 'business message uuid',
    `inputs`           JSON         NULL                    COMMENT 'input variables',
    `query`            TEXT         NOT NULL                COMMENT 'user query',
    `answer`           TEXT         NULL                    COMMENT 'assistant answer',
    `scene_type`       VARCHAR(50)  NULL DEFAULT 'WANMOL'   COMMENT 'scene type',
    `creator_id`       VARCHAR(36)  NULL DEFAULT ''         COMMENT 'creator id',
    `create_time`      DATETIME     NOT NULL                COMMENT 'create time',
    `last_updater_id`  VARCHAR(36)  NULL DEFAULT ''         COMMENT 'last updater id',
    `last_update_time` DATETIME     NOT NULL                COMMENT 'last update time',
    PRIMARY KEY (`id`),
    KEY `ix_agent_message_conversation_id` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='workflow conversation messages';

-- ---------------------------------------------------------------------
-- agent_conv_variable — per-conversation variable pool (JSON blob)
-- Model: src/goalflow/model/wf_conv_variable.py::WorkflowConversationVariables
-- Note: created_at / updated_at map to `create_time` / `last_update_time`.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `agent_conv_variable` (
    `id`               BIGINT       NOT NULL AUTO_INCREMENT,
    `conversation_id`  VARCHAR(36)  NOT NULL                COMMENT 'conversation id',
    `data`             JSON         NOT NULL                COMMENT 'variable data',
    `creator_id`       VARCHAR(36)  NULL DEFAULT ''         COMMENT 'creator id',
    `create_time`      DATETIME     NOT NULL                COMMENT 'create time',
    `last_updater_id`  VARCHAR(36)  NULL DEFAULT ''         COMMENT 'last updater id',
    `last_update_time` DATETIME     NOT NULL                COMMENT 'last update time',
    PRIMARY KEY (`id`),
    KEY `ix_agent_conv_variable_conversation_id` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='workflow conversation variables';

-- ---------------------------------------------------------------------
-- agent_hitl_review — human-in-the-loop review records
-- Model: src/goalflow/model/wf_hitl_review.py::HITLReview
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `agent_hitl_review` (
    `id`               BIGINT        NOT NULL AUTO_INCREMENT,
    `review_id`        VARCHAR(128)  NOT NULL                COMMENT 'review id',
    `workflow_id`      VARCHAR(128)  NOT NULL                COMMENT 'workflow id',
    `workflow_run_id`  VARCHAR(128)  NOT NULL                COMMENT 'workflow run id',
    `checkpoint_name`  VARCHAR(64)   NOT NULL                COMMENT 'checkpoint name',
    `thread_id`        VARCHAR(100)  NOT NULL                COMMENT 'thread id',
    `interrupt_id`     VARCHAR(50)   NOT NULL                COMMENT 'interrupt id',
    `status`           VARCHAR(32)   NOT NULL DEFAULT 'pending'
                                     COMMENT 'status: pending/approved/modified/rejected',
    `data`             JSON          NOT NULL                COMMENT 'data pending review',
    `modified_data`    JSON          NULL                    COMMENT 'modified data',
    `action`           VARCHAR(32)   NULL                    COMMENT 'action: approve/modify/reject',
    `submitted_by`     VARCHAR(36)   NULL                    COMMENT 'reviewer id',
    `created_at`       DATETIME      NOT NULL                COMMENT 'create time',
    `expires_at`       DATETIME      NOT NULL                COMMENT 'expire time',
    `submitted_at`     DATETIME      NULL                    COMMENT 'submit time',
    `updated_at`       DATETIME      NOT NULL                COMMENT 'update time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `ux_agent_hitl_review_review_id` (`review_id`),
    KEY `idx_workflow_id` (`workflow_id`),
    KEY `idx_workflow_run_id` (`workflow_run_id`),
    KEY `idx_status` (`status`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='HITL review records';
