"""M03.1 catalog, typed objective versions and bounded pipeline configuration."""

from datetime import timedelta
from uuid import uuid4

from psycopg import errors
from psycopg.types.json import Jsonb
import pytest

from server.knowledge_authorization import AccessDenied
from server.knowledge_configuration import ConfigurationChanged, install_objective_catalog, save_objective, save_pipeline
from server.knowledge_objectives import (
    FILTERED_CALL, VALIDATED_KNOWLEDGE, TEMPLATES, OutputField, resolve_objective, template_definition,
)
from test_knowledge_foundation import ROOT, _reject, db
from test_knowledge_resource_web import resource_web, runtime
from tools.knowledge_preview_resources import END, START


M010 = ROOT / "database/migrations/010_knowledge_objective_definitions.sql"


def test_curated_catalog_has_six_call_templates_and_one_knowledge_template():
    assert len({template.key for template in TEMPLATES}) == 7
    assert sum(template.input_kind == FILTERED_CALL for template in TEMPLATES) == 6
    content = [template for template in TEMPLATES if template.input_kind == VALIDATED_KNOWLEDGE]
    assert [template.key for template in content] == ["content_opportunities"]
    assert "knowledge_reference" in template_definition(content[0])["output"]["required"]
    price = next(template for template in TEMPLATES if template.key == "price_sensitivity")
    assert template_definition(price)["output"]["properties"]["budget_min"]["type"] == ["string","null"]


def test_structured_custom_objective_rejects_unsupported_or_duplicate_schema():
    field = OutputField("requested_service","text",True)
    kind, output, context = resolve_objective(template_key=None, fields=(field,), context=("destination",))
    assert kind == FILTERED_CALL and output["required"] == ["requested_service"]
    assert output["additionalProperties"] is False and set(context["properties"]) == {"destination"}
    for params in (
        {"template_key": "unknown", "fields": (field,), "context": ()},
        {"template_key": None, "fields": (), "context": ()},
        {"template_key": None, "fields": (field,field), "context": ()},
        {"template_key": None, "fields": (OutputField("value","function",True),), "context": ()},
        {"template_key": None, "fields": (OutputField("value","integer"),), "context": ()},
        {"template_key": None, "fields": (field,), "context": ("arbitrary_js",)},
    ):
        with pytest.raises(ValueError):
            resolve_objective(**params)


@pytest.fixture
def configuration(resource_web):
    s, _, left, right, _, _, _ = resource_web
    db = s["db"]
    with db.transaction():
        _reject(db, errors.RaiseException, M010.read_text(encoding="utf-8"))
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for _ in range(2):
            db.execute(M010.read_text(encoding="utf-8"))
    with pytest.raises(AccessDenied):
        install_objective_catalog(db)
    for _ in range(2):
        install_objective_catalog(db,enabled=True)
    validation, = db.execute("""INSERT INTO panadan_knowledge.policy_versions
        (workspace_id,kind,policy_key,rev,definition,state,approved_by,approved_at)
        VALUES (%s,'validation','synthetic',1,%s,'approved',%s,now()) RETURNING id""",
        (left.workspace,Jsonb({"mode":"synthetic-review"}),s["owner"])).fetchone()
    contract, = db.execute("SELECT current_contract_id FROM panadan_knowledge.sources WHERE id=%s",
                           (left.source,)).fetchone()
    return s, db, left, right, validation, contract


def _objective(config, **changes):
    s, db, left, _, validation, _ = config
    values = dict(workspace=left.workspace,member=s["owner"],key="questions",label="پرسش‌های جدید",
        purpose="ثبت پرسش‌های تکرارشونده",validation_policy=validation,expected_revision=0,
        template_key="customer_questions",enabled=True)
    return save_objective(db, **(values | changes))


def _pipeline(config, objectives, **changes):
    s, db, left, _, _, contract = config
    values = dict(workspace=left.workspace,member=s["owner"],key="daily",label="اجرای نمونه",
        objectives=objectives,source=left.source,contract=contract,operator=left.operator,
        event_start=START,event_end=END,max_resources=20,expected_revision=0,enabled=True)
    return save_pipeline(db, **(values | changes))


def test_versions_preserve_prior_objective_schema_and_pin_the_pipeline(configuration):
    config = configuration
    _, db, left, _, _, _ = config
    assert db.execute("SELECT count(*) FROM panadan_knowledge.objective_templates").fetchone() == (7,)
    objective = _objective(config)
    pipeline = _pipeline(config,(objective.version_id,))
    edited = _objective(config,expected_revision=1,fields=(OutputField("question_exact","text",True),))
    assert edited.definition_id == objective.definition_id and edited.revision == 2
    versions = db.execute("""SELECT o.rev,s.json_schema->'required' FROM panadan_knowledge.objective_versions o
        JOIN panadan_knowledge.attribute_schema_versions s ON s.workspace_id=o.workspace_id AND s.id=o.output_schema_id
        WHERE o.workspace_id=%s AND o.objective_id=%s ORDER BY o.rev""", (left.workspace,objective.definition_id)).fetchall()
    assert versions == [(1,["question"]),(2,["question_exact"])]
    assert db.execute("""SELECT p.enabled,b.objective_version_id FROM panadan_knowledge.pipelines p
        JOIN panadan_knowledge.pipeline_objectives b ON b.workspace_id=p.workspace_id AND b.pipeline_version_id=p.current_version_id
        WHERE p.id=%s""", (pipeline.definition_id,)).fetchone() == (False,objective.version_id)
    with pytest.raises(ConfigurationChanged):
        _objective(config,expected_revision=1)
    custom = _objective(config,key="custom_topic",template_key=None, fields=(OutputField("topic","text",True),))
    assert custom.revision == 1
    newer = _pipeline(config,(edited.version_id,custom.version_id),expected_revision=1)
    assert newer.revision == 2 and newer.definition_id == pipeline.definition_id
    assert db.execute("""SELECT objective_version_id FROM panadan_knowledge.pipeline_objectives
        WHERE workspace_id=%s AND pipeline_version_id=%s ORDER BY stage_order""",
        (left.workspace,newer.version_id)).fetchall() == [(edited.version_id,),(custom.version_id,)]
    _reject(db,errors.RaiseException,"UPDATE panadan_knowledge.objective_versions SET label='changed' WHERE id=%s",
            (objective.version_id,))
    _reject(db,errors.RaiseException,"""UPDATE panadan_knowledge.attribute_schema_versions SET json_schema='{}'
        WHERE workspace_id=%s AND schema_key='output.questions' AND rev=1""", (left.workspace,))
    _reject(db,errors.RaiseException,"DELETE FROM panadan_knowledge.pipeline_sources WHERE pipeline_version_id=%s",
            (pipeline.version_id,))
    _reject(db,errors.ForeignKeyViolation,"""UPDATE panadan_knowledge.objectives SET current_version_id=%s
        WHERE workspace_id=%s AND id=%s""", (custom.version_id,left.workspace,objective.definition_id))


def test_pipeline_denies_invalid_objective_versions_and_unapproved_source_scope(configuration):
    config = configuration
    s, db, _, right, _, _ = config
    first = _objective(config)
    edited = _objective(config,expected_revision=1)
    content = _objective(config,key="content",template_key="content_opportunities")
    for selected, overrides in (
        ((uuid4(),),{}), ((first.version_id,),{}), ((content.version_id,),{}),
        ((edited.version_id,),{"source":right.source}), ((edited.version_id,),{"operator":uuid4()}),
        ((edited.version_id,),{"contract":uuid4()}), ((edited.version_id,),{"member":s["overlap"]}),
        ((edited.version_id,),{"event_start":START+timedelta(days=1),"event_end":END+timedelta(days=1)}),
    ):
        with pytest.raises(AccessDenied):
            _pipeline(config,selected,**overrides)
    with pytest.raises(ValueError,match="30 days"):
        _pipeline(config,(edited.version_id,),event_end=END+timedelta(days=1))
    with pytest.raises(ValueError,match="Duplicate"):
        _pipeline(config,(edited.version_id,edited.version_id))
    assert db.execute("SELECT count(*) FROM panadan_knowledge.pipelines").fetchone() == (0,)


def test_new_configuration_has_no_workspace_runtime_privileges(configuration):
    _, db, _, _, _, _ = configuration
    with db.transaction():
        db.execute("SET LOCAL ROLE panadan_knowledge_reader")
        _reject(db,errors.InsufficientPrivilege,"SELECT * FROM panadan_knowledge.objective_versions")
        _reject(db,errors.InsufficientPrivilege,"SELECT * FROM panadan_knowledge.pipeline_sources")
