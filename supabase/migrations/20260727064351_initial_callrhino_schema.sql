create extension if not exists pgcrypto;

create table public.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null check (char_length(name) between 1 and 120),
    created_by uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now()
);

create table public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null default 'editor'
        check (role in ('owner', 'editor', 'viewer')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create table public.meeting_series (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    name text not null check (char_length(name) between 1 and 160),
    description text,
    default_language_mode text not null default 'codemix'
        check (default_language_mode in ('transcribe', 'translate', 'codemix')),
    created_at timestamptz not null default now(),
    unique (workspace_id, name),
    unique (id, workspace_id)
);

create table public.meetings (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    series_id uuid not null,
    title text not null check (char_length(title) between 1 and 240),
    meeting_date date not null,
    source_type text not null
        check (source_type in ('pasted', 'text_file', 'audio')),
    processing_status text not null default 'draft'
        check (
            processing_status in (
                'draft', 'transcribing', 'extracting', 'review', 'approved', 'failed'
            )
        ),
    raw_transcript text,
    brief jsonb,
    approved_by uuid references auth.users(id) on delete set null,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    unique (id, workspace_id),
    foreign key (series_id, workspace_id)
        references public.meeting_series(id, workspace_id) on delete cascade,
    check (
        processing_status <> 'approved'
        or (brief is not null and approved_by is not null and approved_at is not null)
    )
);

create table public.transcript_segments (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    meeting_id uuid not null,
    segment_key text not null check (segment_key ~ '^seg_[0-9]{4,}$'),
    sequence_no integer not null check (sequence_no > 0),
    speaker_label text,
    start_ms integer check (start_ms is null or start_ms >= 0),
    end_ms integer check (end_ms is null or end_ms >= 0),
    text text not null check (char_length(text) > 0),
    unique (meeting_id, segment_key),
    unique (meeting_id, sequence_no),
    foreign key (meeting_id, workspace_id)
        references public.meetings(id, workspace_id) on delete cascade
);

create table public.decisions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    meeting_id uuid not null,
    series_id uuid not null,
    text text not null check (char_length(text) > 0),
    owner_text text,
    status text not null default 'active'
        check (status in ('active', 'superseded', 'reopened', 'reversed')),
    confidence numeric(4, 3) not null check (confidence between 0 and 1),
    created_at timestamptz not null default now(),
    foreign key (meeting_id, workspace_id)
        references public.meetings(id, workspace_id) on delete cascade,
    foreign key (series_id, workspace_id)
        references public.meeting_series(id, workspace_id) on delete cascade
);

create table public.action_items (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    meeting_id uuid not null,
    series_id uuid not null,
    task text not null check (char_length(task) > 0),
    owner_text text,
    due_date date,
    due_text text,
    priority text not null default 'unknown'
        check (priority in ('low', 'medium', 'high', 'unknown')),
    status text not null default 'open'
        check (status in ('open', 'in_progress', 'blocked', 'done', 'cancelled')),
    confidence numeric(4, 3) not null check (confidence between 0 and 1),
    created_at timestamptz not null default now(),
    foreign key (meeting_id, workspace_id)
        references public.meetings(id, workspace_id) on delete cascade,
    foreign key (series_id, workspace_id)
        references public.meeting_series(id, workspace_id) on delete cascade
);

create table public.open_questions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    meeting_id uuid not null,
    series_id uuid not null,
    text text not null check (char_length(text) > 0),
    status text not null default 'open' check (status in ('open', 'resolved')),
    confidence numeric(4, 3) not null check (confidence between 0 and 1),
    created_at timestamptz not null default now(),
    foreign key (meeting_id, workspace_id)
        references public.meetings(id, workspace_id) on delete cascade,
    foreign key (series_id, workspace_id)
        references public.meeting_series(id, workspace_id) on delete cascade
);

create table public.risks (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    meeting_id uuid not null,
    series_id uuid not null,
    text text not null check (char_length(text) > 0),
    created_at timestamptz not null default now(),
    foreign key (meeting_id, workspace_id)
        references public.meetings(id, workspace_id) on delete cascade,
    foreign key (series_id, workspace_id)
        references public.meeting_series(id, workspace_id) on delete cascade
);

create table public.evidence_refs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    segment_id uuid not null references public.transcript_segments(id) on delete cascade,
    entity_type text not null
        check (entity_type in ('decision', 'action_item', 'open_question', 'risk')),
    entity_id uuid not null,
    quote text not null check (char_length(quote) between 1 and 1200),
    created_at timestamptz not null default now()
);

create table public.item_links (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    series_id uuid not null,
    source_type text not null check (source_type in ('decision', 'action_item')),
    source_id uuid not null,
    target_type text not null check (target_type in ('decision', 'action_item')),
    target_id uuid not null,
    relationship text not null
        check (
            relationship in ('repeats', 'continues', 'supersedes', 'contradicts', 'resolves')
        ),
    confidence numeric(4, 3) not null check (confidence between 0 and 1),
    is_confirmed boolean not null default false,
    created_at timestamptz not null default now(),
    foreign key (series_id, workspace_id)
        references public.meeting_series(id, workspace_id) on delete cascade
);

create table public.processing_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    meeting_id uuid not null,
    stage text not null check (stage in ('transcription', 'extraction', 'reconciliation')),
    provider text not null default 'sarvam',
    model text not null,
    prompt_version text,
    schema_version text,
    status text not null check (status in ('started', 'succeeded', 'failed')),
    input_tokens integer check (input_tokens is null or input_tokens >= 0),
    output_tokens integer check (output_tokens is null or output_tokens >= 0),
    estimated_cost_inr numeric(12, 6)
        check (estimated_cost_inr is null or estimated_cost_inr >= 0),
    error_code text,
    created_at timestamptz not null default now(),
    foreign key (meeting_id, workspace_id)
        references public.meetings(id, workspace_id) on delete cascade
);

create index workspace_members_user_idx
    on public.workspace_members(user_id, workspace_id);
create index meeting_series_workspace_idx
    on public.meeting_series(workspace_id, created_at desc);
create index meetings_series_date_idx
    on public.meetings(series_id, meeting_date desc);
create index transcript_segments_meeting_idx
    on public.transcript_segments(meeting_id, sequence_no);
create index decisions_series_status_idx
    on public.decisions(series_id, status);
create index action_items_series_status_due_idx
    on public.action_items(series_id, status, due_date);
create index open_questions_series_status_idx
    on public.open_questions(series_id, status);
create index item_links_series_idx
    on public.item_links(series_id, relationship);
create index processing_runs_meeting_idx
    on public.processing_runs(meeting_id, created_at desc);

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.meeting_series enable row level security;
alter table public.meetings enable row level security;
alter table public.transcript_segments enable row level security;
alter table public.decisions enable row level security;
alter table public.action_items enable row level security;
alter table public.open_questions enable row level security;
alter table public.risks enable row level security;
alter table public.evidence_refs enable row level security;
alter table public.item_links enable row level security;
alter table public.processing_runs enable row level security;

create policy "workspace creators can insert workspaces"
on public.workspaces for insert
to authenticated
with check ((select auth.uid()) = created_by);

create policy "members can view workspaces"
on public.workspaces for select
to authenticated
using (
    created_by = (select auth.uid())
    or exists (
        select 1
        from public.workspace_members member
        where member.workspace_id = workspaces.id
          and member.user_id = (select auth.uid())
    )
);

create policy "workspace creators can update workspaces"
on public.workspaces for update
to authenticated
using (created_by = (select auth.uid()))
with check (created_by = (select auth.uid()));

create policy "users can view their own memberships"
on public.workspace_members for select
to authenticated
using (user_id = (select auth.uid()));

create policy "workspace creators can add members"
on public.workspace_members for insert
to authenticated
with check (
    exists (
        select 1
        from public.workspaces workspace
        where workspace.id = workspace_members.workspace_id
          and workspace.created_by = (select auth.uid())
    )
);

create policy "workspace creators can update members"
on public.workspace_members for update
to authenticated
using (
    exists (
        select 1
        from public.workspaces workspace
        where workspace.id = workspace_members.workspace_id
          and workspace.created_by = (select auth.uid())
    )
)
with check (
    exists (
        select 1
        from public.workspaces workspace
        where workspace.id = workspace_members.workspace_id
          and workspace.created_by = (select auth.uid())
    )
);

create policy "workspace creators can remove members"
on public.workspace_members for delete
to authenticated
using (
    exists (
        select 1
        from public.workspaces workspace
        where workspace.id = workspace_members.workspace_id
          and workspace.created_by = (select auth.uid())
    )
);

do $policies$
declare
    table_name text;
begin
    foreach table_name in array array[
        'meeting_series',
        'meetings',
        'transcript_segments',
        'decisions',
        'action_items',
        'open_questions',
        'risks',
        'evidence_refs',
        'item_links',
        'processing_runs'
    ]
    loop
        execute format(
            'create policy "members can view %1$s" on public.%1$I for select '
            'to authenticated using (exists (select 1 from public.workspace_members member '
            'where member.workspace_id = %1$I.workspace_id '
            'and member.user_id = (select auth.uid())))',
            table_name
        );
        execute format(
            'create policy "editors can insert %1$s" on public.%1$I for insert '
            'to authenticated with check (exists (select 1 from public.workspace_members member '
            'where member.workspace_id = %1$I.workspace_id '
            'and member.user_id = (select auth.uid()) '
            'and member.role in (''owner'', ''editor'')))',
            table_name
        );
        execute format(
            'create policy "editors can update %1$s" on public.%1$I for update '
            'to authenticated using (exists (select 1 from public.workspace_members member '
            'where member.workspace_id = %1$I.workspace_id '
            'and member.user_id = (select auth.uid()) '
            'and member.role in (''owner'', ''editor''))) '
            'with check (exists (select 1 from public.workspace_members member '
            'where member.workspace_id = %1$I.workspace_id '
            'and member.user_id = (select auth.uid()) '
            'and member.role in (''owner'', ''editor'')))',
            table_name
        );
        execute format(
            'create policy "editors can delete %1$s" on public.%1$I for delete '
            'to authenticated using (exists (select 1 from public.workspace_members member '
            'where member.workspace_id = %1$I.workspace_id '
            'and member.user_id = (select auth.uid()) '
            'and member.role in (''owner'', ''editor'')))',
            table_name
        );
    end loop;
end
$policies$;

grant usage on schema public to authenticated;
grant select, insert, update, delete on table
    public.workspaces,
    public.workspace_members,
    public.meeting_series,
    public.meetings,
    public.transcript_segments,
    public.decisions,
    public.action_items,
    public.open_questions,
    public.risks,
    public.evidence_refs,
    public.item_links,
    public.processing_runs
to authenticated;

revoke all on table
    public.workspaces,
    public.workspace_members,
    public.meeting_series,
    public.meetings,
    public.transcript_segments,
    public.decisions,
    public.action_items,
    public.open_questions,
    public.risks,
    public.evidence_refs,
    public.item_links,
    public.processing_runs
from anon;
