-- GameGuide AI: esquema y migraciones idempotentes para Supabase.
create extension if not exists pgcrypto;
create extension if not exists vector;

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
  updated_at timestamptz not null default now(),
  embedding vector(384)
);
alter table public.knowledge_documents add column if not exists embedding vector(384);
create index if not exists knowledge_documents_retrieved_at_idx
  on public.knowledge_documents (retrieved_at desc);
create index if not exists knowledge_documents_embedding_idx
  on public.knowledge_documents using ivfflat (embedding vector_cosine_ops) with (lists = 100);

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
  is_public boolean not null default true,
  question_embedding vector(384),
  created_at timestamptz not null default now()
);
alter table public.chat_interactions add column if not exists is_public boolean not null default true;
alter table public.chat_interactions add column if not exists question_embedding vector(384);
create index if not exists chat_interactions_created_at_idx
  on public.chat_interactions (created_at desc);
create index if not exists chat_interactions_session_id_idx
  on public.chat_interactions (session_id);
create index if not exists chat_interactions_public_idx
  on public.chat_interactions (is_public, created_at desc);

-- Likes/dislikes: un usuario/dispositivo puede cambiar su voto, pero no duplicarlo.
create table if not exists public.chat_votes (
  id uuid primary key default gen_random_uuid(),
  interaction_id uuid not null references public.chat_interactions(id) on delete cascade,
  voter_id text not null,
  vote text not null check (vote in ('like','dislike')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(interaction_id, voter_id)
);
create index if not exists chat_votes_interaction_idx on public.chat_votes(interaction_id);
create index if not exists chat_votes_created_at_idx on public.chat_votes(created_at desc);

-- Migra las valoraciones antiguas a votos y elimina la tabla de comentarios.
do $$
begin
  if to_regclass('public.chat_feedback') is not null then
    execute $migrate$
      insert into public.chat_votes (interaction_id, voter_id, vote, created_at)
      select interaction_id, 'legacy-' || id::text,
             case when rating = 'si_me_ayudo' then 'like' else 'dislike' end,
             created_at
      from public.chat_feedback
      on conflict (interaction_id, voter_id) do nothing
    $migrate$;
    drop table public.chat_feedback;
  end if;
end $$;

-- Búsqueda semántica por similitud coseno.
create or replace function public.match_knowledge_documents(
  query_embedding vector(384),
  match_count int default 8
)
returns table (
  source_id text,
  source_name text,
  source_type text,
  title text,
  content text,
  url text,
  category text,
  game_version text,
  source_updated_at text,
  retrieved_at timestamptz,
  similarity double precision
)
language sql stable
as $$
  select kd.source_id, kd.source_name, kd.source_type, kd.title, kd.content,
         kd.url, kd.category, kd.game_version, kd.source_updated_at,
         kd.retrieved_at,
         1 - (kd.embedding <=> query_embedding) as similarity
  from public.knowledge_documents kd
  where kd.embedding is not null
  order by kd.embedding <=> query_embedding
  limit greatest(1, least(match_count, 50));
$$;

-- El backend usa SUPABASE_SERVICE_ROLE_KEY; nunca exponerla en Vue.


create index if not exists chat_interactions_question_embedding_idx
  on public.chat_interactions using ivfflat (question_embedding vector_cosine_ops) with (lists = 100);

-- Recupera respuestas previas para preguntas equivalentes (mismo juego/edición cuando se especifican).
create or replace function public.match_chat_interactions(
  query_embedding vector(384),
  match_threshold double precision default 0.88,
  match_count int default 1,
  edition_filter text default null,
  game_version_filter text default null
)
returns table (
  id uuid,
  question text,
  answer text,
  category text,
  edition text,
  game_version text,
  sources jsonb,
  model_used text,
  created_at timestamptz,
  similarity double precision
)
language sql stable
as $$
  select ci.id, ci.question, ci.answer, ci.category, ci.edition, ci.game_version,
         ci.sources, ci.model_used, ci.created_at,
         1 - (ci.question_embedding <=> query_embedding) as similarity
  from public.chat_interactions ci
  where ci.question_embedding is not null
    and ci.is_public = true
    and (edition_filter is null or ci.edition = edition_filter)
    and (game_version_filter is null or ci.game_version = game_version_filter)
    and 1 - (ci.question_embedding <=> query_embedding) >= match_threshold
  order by ci.question_embedding <=> query_embedding
  limit greatest(1, least(match_count, 10));
$$;
