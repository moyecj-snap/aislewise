create extension if not exists pgcrypto;

create table if not exists public.wines (
  id uuid primary key default gen_random_uuid(),
  display_name text not null,
  producer text,
  normalized_name text not null,
  aliases text[] default '{}',
  varietal text,
  region text,
  country text,
  avg_price numeric,
  price_band text,
  rating_estimate numeric,
  pairing_tags text[] default '{}',
  occasion_tags text[] default '{}',
  style text,
  crowd_pleaser_score int,
  value_score int,
  known_retailers text[] default '{}',
  label_keywords text[] default '{}',
  created_at timestamptz default now()
);

create index if not exists wines_normalized_name_idx on public.wines (normalized_name);
create index if not exists wines_varietal_idx on public.wines (varietal);
create index if not exists wines_pairing_tags_idx on public.wines using gin (pairing_tags);
create index if not exists wines_occasion_tags_idx on public.wines using gin (occasion_tags);
create index if not exists wines_known_retailers_idx on public.wines using gin (known_retailers);

create table if not exists public.scan_sessions (
  id uuid primary key default gen_random_uuid(),
  budget text not null,
  food text,
  occasion text,
  store_name text,
  source text default 'photo',
  created_at timestamptz default now()
);

create table if not exists public.detected_wines (
  id uuid primary key default gen_random_uuid(),
  scan_session_id uuid references public.scan_sessions(id) on delete cascade,
  wine_id uuid references public.wines(id),
  raw_name text,
  detected_price numeric,
  confidence numeric,
  created_at timestamptz default now()
);

create table if not exists public.recommendations (
  id uuid primary key default gen_random_uuid(),
  scan_session_id uuid references public.scan_sessions(id) on delete cascade,
  wine_id uuid references public.wines(id),
  rank int not null,
  score numeric not null,
  reasons text[] default '{}',
  created_at timestamptz default now()
);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  scan_session_id uuid references public.scan_sessions(id) on delete set null,
  wine_id uuid references public.wines(id) on delete set null,
  feedback_type text not null,
  note text,
  created_at timestamptz default now()
);

alter table public.wines enable row level security;
alter table public.scan_sessions enable row level security;
alter table public.detected_wines enable row level security;
alter table public.recommendations enable row level security;
alter table public.feedback enable row level security;

drop policy if exists "Public can read wines" on public.wines;
create policy "Public can read wines"
on public.wines for select
using (true);
