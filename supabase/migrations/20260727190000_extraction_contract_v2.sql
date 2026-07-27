alter table public.decisions
    add column outcome_status text not null default 'confirmed'
        check (
            outcome_status in (
                'confirmed', 'tentative', 'deferred', 'rejected', 'reversed'
            )
        ),
    add column decision_maker_text text,
    add column decision_maker_basis text not null default 'unassigned'
        check (
            decision_maker_basis in (
                'explicit', 'group', 'reviewer_confirmed', 'unassigned'
            )
        ),
    add column effective_date date,
    add column effective_date_text text,
    add column date_precision text not null default 'absent'
        check (
            date_precision in ('exact', 'resolved_relative', 'vague', 'absent')
        ),
    add column evidence_strength text not null default 'strong_context'
        check (evidence_strength in ('explicit', 'strong_context', 'ambiguous'));

update public.decisions
set
    decision_maker_text = owner_text,
    decision_maker_basis = case
        when owner_text is null then 'unassigned'
        else 'reviewer_confirmed'
    end;

alter table public.decisions
    alter column confidence drop not null;

alter table public.action_items
    add column commitment_status text not null default 'requested'
        check (
            commitment_status in ('committed', 'conditional', 'requested', 'blocked')
        ),
    add column owner_basis text not null default 'unassigned'
        check (
            owner_basis in (
                'self_commitment',
                'assigned_and_accepted',
                'group_commitment',
                'reviewer_confirmed',
                'unassigned'
            )
        ),
    add column suggested_owner_text text,
    add column deadline_precision text not null default 'absent'
        check (
            deadline_precision in ('exact', 'resolved_relative', 'vague', 'absent')
        ),
    add column evidence_strength text not null default 'strong_context'
        check (evidence_strength in ('explicit', 'strong_context', 'ambiguous'));

update public.action_items
set
    commitment_status = case
        when owner_text is null then 'requested'
        else 'committed'
    end,
    owner_basis = case
        when owner_text is null then 'unassigned'
        else 'reviewer_confirmed'
    end,
    deadline_precision = case
        when due_date is not null and due_text is not null then 'resolved_relative'
        when due_date is not null then 'exact'
        when due_text is not null then 'vague'
        else 'absent'
    end;

alter table public.action_items
    alter column confidence drop not null;

alter table public.open_questions
    add column question_status text not null default 'open'
        check (question_status in ('open', 'deferred')),
    add column evidence_strength text not null default 'strong_context'
        check (evidence_strength in ('explicit', 'strong_context', 'ambiguous'));

alter table public.open_questions
    alter column confidence drop not null;

alter table public.risks
    add column risk_kind text not null default 'risk'
        check (risk_kind in ('risk', 'blocker', 'dependency')),
    add column evidence_strength text not null default 'strong_context'
        check (evidence_strength in ('explicit', 'strong_context', 'ambiguous'));
