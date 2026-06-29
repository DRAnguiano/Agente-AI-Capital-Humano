-- Índice único para idempotencia de save_message.
-- Garantiza que un mismo mensaje (misma clave de conversación, rol y contenido)
-- no se inserte dos veces, haciendo la persistencia compatible con ON CONFLICT DO NOTHING.
CREATE UNIQUE INDEX IF NOT EXISTS uq_rh_messages_conv_role_msg
    ON rh_messages (conversation_key, role, message);
