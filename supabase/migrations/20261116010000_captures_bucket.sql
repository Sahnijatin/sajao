-- Interim home for capture uploads (approved scope change): a private bucket
-- in Supabase Storage. The API signs multipart uploads with the caller's own
-- session, so these policies are what keep a user inside their own folder:
-- every object key starts with the owner's user id.
--
-- Skipped where there is no storage schema (the plain Postgres used in tests).
do $migration$
begin
    if to_regnamespace('storage') is null then
        return;
    end if;

    -- Private. One file is at most 50 MiB, the project's own limit.
    insert into storage.buckets (id, name, public, file_size_limit)
    values ('captures', 'captures', false, 52428800)
    on conflict (id) do nothing;

    -- A signed-in user (guests included) writes and reads only under their
    -- own user id. The caller's id is read once per query, not once per row.
    execute $policy$
        create policy captures_objects_insert_own on storage.objects
            for insert to authenticated
            with check (
                bucket_id = 'captures'
                and (storage.foldername(name))[1] = (select auth.uid())::text
            )
    $policy$;
    execute $policy$
        create policy captures_objects_select_own on storage.objects
            for select to authenticated
            using (
                bucket_id = 'captures'
                and (storage.foldername(name))[1] = (select auth.uid())::text
            )
    $policy$;
end
$migration$;
