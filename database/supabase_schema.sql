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

-- Recupera respuestas previas SOLO para preguntas casi idénticas:
--  * misma edición y misma versión (una versión vacía solo coincide con versión vacía),
--  * con evidencia (nunca reutiliza respuestas sin fuentes),
--  * sin ningún dislike.
create or replace function public.match_chat_interactions(
  query_embedding vector(384),
  match_threshold double precision default 0.93,
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
    and ci.evidence = true
    and (edition_filter is null or ci.edition = edition_filter)
    and ci.game_version is not distinct from game_version_filter
    and not exists (
      select 1 from public.chat_votes v
      where v.interaction_id = ci.id and v.vote = 'dislike'
    )
    and 1 - (ci.question_embedding <=> query_embedding) >= match_threshold
  order by ci.question_embedding <=> query_embedding
  limit greatest(1, least(match_count, 10));
$$;

-- ============================================================================
-- v1.1  Recuperación por FRAGMENTOS (chunks) con umbral de similitud
-- ============================================================================
-- Cada documento se divide en fragmentos de ~800 caracteres; cada fragmento tiene su propio
-- vector. Así el embedding representa un pasaje concreto y no una página completa.
create table if not exists public.knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  source_id text not null,
  chunk_index int not null,
  source_name text not null,
  source_type text not null,
  title text not null,
  content text not null,
  url text not null,
  category text default 'general',
  game_version text,
  retrieved_at timestamptz not null default now(),
  embedding vector(384),
  unique (source_id, chunk_index)
);
create index if not exists knowledge_chunks_source_idx on public.knowledge_chunks (source_id);
create index if not exists knowledge_chunks_retrieved_at_idx on public.knowledge_chunks (retrieved_at desc);
create index if not exists knowledge_chunks_embedding_idx
  on public.knowledge_chunks using hnsw (embedding vector_cosine_ops);

create or replace function public.match_knowledge_chunks(
  query_embedding vector(384),
  match_count int default 12,
  min_similarity double precision default 0.30,
  max_age_days int default 14
)
returns table (
  source_id text,
  chunk_index int,
  source_name text,
  source_type text,
  title text,
  content text,
  url text,
  category text,
  game_version text,
  retrieved_at timestamptz,
  similarity double precision
)
language sql stable
as $$
  select kc.source_id, kc.chunk_index, kc.source_name, kc.source_type, kc.title, kc.content,
         kc.url, kc.category, kc.game_version, kc.retrieved_at,
         1 - (kc.embedding <=> query_embedding) as similarity
  from public.knowledge_chunks kc
  where kc.embedding is not null
    and kc.retrieved_at >= now() - make_interval(days => max_age_days)
    and 1 - (kc.embedding <=> query_embedding) >= min_similarity
  order by kc.embedding <=> query_embedding
  limit greatest(1, least(match_count, 50));
$$;

-- ============================================================================
-- Métricas del dashboard calculadas en SQL (antes se descargaban hasta 5,000 filas)
-- ============================================================================
create or replace function public.dashboard_metrics(days int default 30)
returns jsonb
language sql stable
as $$
  with i as (
    select * from public.chat_interactions where created_at >= now() - make_interval(days => days)
  ), v as (
    select * from public.chat_votes where created_at >= now() - make_interval(days => days)
  )
  select jsonb_build_object(
    'total',          (select count(*) from i),
    'total_feedback', (select count(*) from v),
    'likes',          (select count(*) from v where vote = 'like'),
    'dislikes',       (select count(*) from v where vote = 'dislike'),
    'avg_ms',         (select avg(response_ms) from i where response_ms is not null),
    'with_evidence',  (select count(*) from i where evidence or jsonb_array_length(sources) > 0),
    'reused',         (select count(*) from i where reused_knowledge),
    'categories',     coalesce((select jsonb_object_agg(cat, n) from (
                        select coalesce(category, 'general') as cat, count(*) as n from i group by 1) t), '{}'::jsonb),
    'daily',          coalesce((select jsonb_agg(jsonb_build_object('date', d, 'count', n) order by d) from (
                        select to_char(created_at::date, 'YYYY-MM-DD') as d, count(*) as n from i group by 1) t), '[]'::jsonb)
  );
$$;

-- ============================================================================
-- Seguridad: RLS activado. El backend usa SUPABASE_SERVICE_ROLE_KEY (que ignora RLS);
-- si algún día se expone la llave anónima, las tablas quedan cerradas por defecto.
-- ============================================================================
alter table public.knowledge_documents enable row level security;
alter table public.knowledge_chunks    enable row level security;
alter table public.chat_interactions   enable row level security;
alter table public.chat_votes          enable row level security;
