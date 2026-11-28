"""Read-only projections of real synthetic configuration and run effects."""

from .knowledge_authorization import AccessDenied


PAGES = {"objectives":"objective.configure", "pipelines":"pipeline.configure", "runs":"pipeline.run"}


def studio_view(db, workspace, page):
    if page == "objectives":
        objectives = db.execute("""SELECT v.label,v.purpose,v.rev,v.input_kind,v.state,t.label AS template
            FROM panadan_knowledge.objectives o JOIN panadan_knowledge.objective_versions v
              ON v.workspace_id=o.workspace_id AND v.id=o.current_version_id
            LEFT JOIN panadan_knowledge.objective_templates t ON t.id=v.template_id
            WHERE o.workspace_id=%s ORDER BY v.label,o.id LIMIT 30""",(workspace,)).fetchall()
        templates = db.execute("""SELECT label,input_kind FROM panadan_knowledge.objective_templates
            WHERE state='active' ORDER BY template_key,rev DESC LIMIT 30""").fetchall()
        return {"objectives":objectives,"objective_templates":templates}
    if page == "pipelines":
        pipelines = db.execute("""SELECT v.id,v.label,v.rev,v.processor,v.max_resources,v.event_start,v.event_end,p.enabled,
                s.label AS source,coalesce(o.label,o.external_operator_key) AS operator
            FROM panadan_knowledge.pipelines p JOIN panadan_knowledge.pipeline_versions v
              ON v.workspace_id=p.workspace_id AND v.id=p.current_version_id
            JOIN panadan_knowledge.pipeline_sources b ON b.workspace_id=v.workspace_id AND b.pipeline_version_id=v.id
            JOIN panadan_knowledge.sources s ON s.workspace_id=b.workspace_id AND s.id=b.source_id
            JOIN panadan_knowledge.operator_scopes o ON o.workspace_id=b.workspace_id AND o.id=b.operator_scope_id
            WHERE p.workspace_id=%s AND s.state='active' AND o.state='active'
            ORDER BY v.label,v.id LIMIT 30""",(workspace,)).fetchall()
        schedules = db.execute("""SELECT v.label,s.enabled,s.next_due_at,s.cadence_seconds
            FROM panadan_knowledge.schedules s JOIN panadan_knowledge.pipeline_versions v
              ON v.workspace_id=s.workspace_id AND v.id=s.pipeline_version_id
            WHERE s.workspace_id=%s ORDER BY s.next_due_at LIMIT 30""",(workspace,)).fetchall()
        return {"pipelines":pipelines,"schedules":schedules}
    if page == "runs":
        runs = db.execute("""SELECT v.label,v.rev,r.state,r.trigger_kind,r.created_at,r.finished_at,
              c.measured_count,c.ready_count,c.excluded_count,c.source_eligible_count,c.bounded,
              work.succeeded,work.failed,work.open
            FROM panadan_knowledge.runs r JOIN panadan_knowledge.pipeline_versions v
              ON v.workspace_id=r.workspace_id AND v.id=r.pipeline_version_id
            JOIN panadan_knowledge.coverage_snapshots c ON c.workspace_id=r.workspace_id AND c.run_id=r.id AND c.stage='admission'
            LEFT JOIN LATERAL (
              SELECT count(*) FILTER (WHERE state='succeeded') AS succeeded,
                     count(*) FILTER (WHERE state IN ('failed','blocked_policy')) AS failed,
                     count(*) FILTER (WHERE state IN ('queued','running','retry_wait','paused')) AS open
              FROM panadan_knowledge.work_items i WHERE i.workspace_id=r.workspace_id AND i.run_id=r.id
            ) work ON true
            WHERE r.workspace_id=%s ORDER BY r.created_at DESC,r.id DESC LIMIT 30""",(workspace,)).fetchall()
        return {"runs":runs}
    raise AccessDenied("Access denied")
