"""Make completed, deterministic runs visible in the isolated Studio preview."""

from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from server.knowledge_configuration import install_objective_catalog, save_objective, save_pipeline
from server.knowledge_durable_work import claim_work, finish_work, reconcile_run, start_run
from server.knowledge_objectives import OutputField
from server.knowledge_run_admission import create_schedule, request_run, set_pipeline_enabled
from tools.knowledge_preview_resources import END, START, _connect


def seed_preview_studio(port, scopes, administrators):
    with _connect(port,"panadan_ci") as db:
        install_objective_catalog(db,enabled=True)
        for index,(scope,member) in enumerate(zip(scopes,administrators,strict=True)):
            config = dict(workspace=scope.workspace,member=member,enabled=True)
            validation, = db.execute("""INSERT INTO panadan_knowledge.policy_versions
                (workspace_id,kind,policy_key,rev,definition,state,approved_by,approved_at)
                VALUES (%s,'validation','synthetic',1,%s,'approved',%s,now()) RETURNING id""",
                (scope.workspace,Jsonb({"mode":"synthetic-review"}),member)).fetchone()
            questions = save_objective(db,**config,key="questions",label="پرسش‌های رزرو" if index==0 else "پرسش‌های پشتیبانی",
                purpose="ثبت موضوع پرسش‌های مطرح‌شده در تماس‌ها",validation_policy=validation,expected_revision=0,
                template_key="customer_questions")
            custom = save_objective(db,**config,key="requested_change",label="درخواست تغییر",
                purpose="ثبت نوع تغییر درخواستی در تماس",validation_policy=validation,expected_revision=0,
                fields=(OutputField("requested_change","text",True),))
            contract, = db.execute("""SELECT current_contract_id FROM panadan_knowledge.sources
                WHERE workspace_id=%s AND id=%s""",(scope.workspace,scope.source)).fetchone()
            pipeline = save_pipeline(db,**config,key="synthetic_calls",label="پردازش تماس‌های رزرو" if index==0 else "پردازش تماس‌های پشتیبانی",
                objectives=(questions.version_id,custom.version_id),source=scope.source,contract=contract,operator=scope.operator,
                event_start=START,event_end=END,max_resources=50,expected_revision=0)
            definition = config | {"pipeline_version":pipeline.version_id}
            set_pipeline_enabled(db,**definition,activate=True)
            tomorrow, = db.execute("SELECT clock_timestamp()+interval '1 day'").fetchone()
            create_schedule(db,**definition,key="daily",first_due_at=tomorrow,cadence_seconds=int(timedelta(days=1).total_seconds()))
            run = request_run(db,**definition,request_key=uuid4())
            work = config | {"run_id":run.run_id}
            start_run(db,**work)
            worker = uuid4()
            for _ in range(run.ready):
                lease = claim_work(db,**work,worker_id=worker)
                if lease is None or finish_work(db,**work,lease=lease)!="succeeded":
                    raise RuntimeError("Synthetic Studio work failed")
            if reconcile_run(db,**work) not in ("succeeded","partial"):
                raise RuntimeError("Synthetic Studio run did not finish")
