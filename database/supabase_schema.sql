-- Esquema esperado por GameGuide AI. Ejecuta este script en Supabase > SQL Editor.
create extension if not exists pgcrypto;

create table if not exists public.knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  source_id text not null unique,
  source_name text not null,
  source_type text not null,
  title text not null,
  content text not null,
  url text not null,
  category text default 'general',
  game_version text,
  source_updated_at text,
  retrieved_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists knowledge_documents_retrieved_at_idx
  on public.knowledge_documents (retrieved_at desc);

create table if not exists public.chat_interactions (
  id uuid primary key default gen_random_uuid(),
  session_id text not null,
  question text not null,
  answer text not null,
  category text,
  edition text,
  game_version text,
  model_used text,
  response_ms integer,
  sources jsonb not null default '[]'::jsonb,
  retrieved_count integer not null default 0,
  evidence boolean not null default false,
  reused_knowledge boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists chat_interactions_created_at_idx
  on public.chat_interactions (created_at desc);
create index if not exists chat_interactions_session_id_idx
  on public.chat_interactions (session_id);

create table if not exists public.chat_feedback (
  id uuid primary key default gen_random_uuid(),
  interaction_id uuid not null references public.chat_interactions(id) on delete cascade,
  rating text not null check (rating in ('si_me_ayudo','no_entrego_justo','nada_que_ver')),
  comment text,
  created_at timestamptz not null default now()
);
create index if not exists chat_feedback_created_at_idx
  on public.chat_feedback (created_at desc);
create index if not exists chat_feedback_interaction_id_idx
  on public.chat_feedback (interaction_id);

-- Las claves privadas se mantienen exclusivamente en backend/.env.
-- El backend usa SUPABASE_SERVICE_ROLE_KEY y nunca la expone al navegador.
