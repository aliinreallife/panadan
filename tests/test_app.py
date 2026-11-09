import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    # Import after setting the auth DB path. Never connect to real PostgreSQL.
    monkeypatch.setenv('PANADAN_AUTH_DB',str(tmp_path/'auth.sqlite'))
    monkeypatch.setenv('PANADAN_ADMIN_USER','admin')
    monkeypatch.setenv('PANADAN_ADMIN_PASSWORD','a-long-safe-testing-password')
    monkeypatch.setenv('PANADAN_COOKIE_SECURE','false')
    import importlib, server.main as main
    # TestClient mocks data access. No business data or DB credentials required.
    main = importlib.reload(main)
    monkeypatch.setattr(main.database, 'list_calls',lambda *a,**k:[{'id':5,'CALLDATE':'2026-10-01','aicallinfostate':'Unchecked'}])
    monkeypatch.setattr(main.database, 'get_call',lambda *a,**k:{'id':5,'summary':'synthetic'} if k.get('sensitive') else {'id':5})
    monkeypatch.setattr(main.database, 'stats',lambda *a,**k:{'total':1,'sold_out':0,'scored_calls':1,'avg_ai_score':10,'avg_voice_length':20})
    monkeypatch.setattr(main.database, 'statuses',lambda *a,**k:['Unchecked','System Invalid'])
    monkeypatch.setattr(main.database, 'call_types',lambda *a,**k:['FollowUp','FirstToch'])
    monkeypatch.setattr(main.database, 'directions',lambda *a,**k:['Incoming','Outgoing'])
    monkeypatch.setattr(main.database, 'operators',lambda *a,**k:['__unspecified__','Test Op','Other Op'])
    # Exercise dashboard/API permissions without restarting the singleton MCP
    # session manager, which the MCP SDK permits to run only once per process.
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def auth_test_lifespan(_app):
        main.store.bootstrap('admin', 'a-long-safe-testing-password')
        yield
    main.app.router.lifespan_context = auth_test_lifespan
    with TestClient(main.app) as c: yield c, main


def test_reject_unauthorized(client):
    c,_=client
    assert c.get('/api/v1/calls').status_code==401
    assert c.get('/dashboard/data').status_code==401
    assert c.post('/mcp/',json={}).status_code==401


def test_login_dashboard_and_revoke(client):
    c,main=client
    html=c.get('/login').text
    import re
    nonce=re.search(r'name="nonce" value="([^"]+)"',html).group(1)
    r=c.post('/login',data={'username':'admin','password':'a-long-safe-testing-password','nonce':nonce},follow_redirects=False)
    assert r.status_code==303
    assert c.get('/dashboard').status_code==200
    assert c.get('/dashboard/data').json()['items'][0]['id']==5
    csrf=main.store.session(c.cookies.get('panadan_session'))['csrf']
    r=c.post('/dashboard/tokens',data={'name':'test','scope':'api:read','days':7,'csrf':csrf})
    assert r.status_code==200
    assert 'panadan_' in r.text
    assert len(main.store.list_tokens())==1
    tid=main.store.list_tokens()[0]['id']
    assert c.post(f'/dashboard/tokens/{tid}/revoke',data={'csrf':'invalid'}).status_code==403
    assert c.post(f'/dashboard/tokens/{tid}/revoke',data={'csrf':csrf},follow_redirects=False).status_code==303
    assert not main.store.list_tokens()


def test_dashboard_only_cannot_bypass_sensitive_detail(client):
    c, main = client
    uid=main.store.create_user('callreader','another-long-password','reader',['calls:read'])
    raw,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',raw)
    r=c.get('/dashboard/data/5')
    assert r.status_code==200
    assert 'summary' not in r.json()
    assert c.get('/dashboard/users').status_code==403

def test_stats_only_api_token(client):
    c, main = client
    uid=main.store.create_user('metricsonly','another-long-password','metrics',['metrics:read'])
    _, token=main.store.create_token('stats only','api:read',30,uid)
    headers={'Authorization':'Bearer '+token}
    assert c.get('/api/v1/stats',headers=headers).status_code==200
    assert c.get('/api/v1/calls',headers=headers).status_code==401
    assert c.get('/api/v1/calls/5',headers=headers).status_code==401

def test_filters_and_api_guide_require_session_permissions(client):
    c,main=client
    assert c.get('/dashboard/api').status_code == 401
    assert c.get('/dashboard/filter-options').status_code == 401
    admin = main.store.verify_login('admin','a-long-safe-testing-password')
    cookie,_=main.store.create_session(admin)
    c.cookies.set('panadan_session',cookie)
    guide=c.get('/dashboard/api')
    assert guide.status_code == 200
    assert 'Swagger UI' in guide.text
    assert 'call_type=FollowUp' in guide.text
    options=c.get('/dashboard/filter-options')
    assert options.status_code == 200
    assert options.json()['call_types'] == ['FollowUp','FirstToch']
    assert 'System Invalid' in options.json()['states']
    assert c.get('/dashboard/data?call_type=FollowUp&state=Unchecked').status_code == 200

def test_metrics_user_cannot_read_call_filter_values_or_api_guide(client):
    c,main=client
    uid=main.store.create_user('metrics-only', 'another-long-password', 'metrics', ['metrics:read'])
    cookie,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',cookie)
    assert c.get('/dashboard/filter-options').status_code == 403
    assert c.get('/dashboard/api').status_code == 403
    assert c.get('/dashboard/metrics').status_code == 200


def test_browser_overview_only_uses_public_columns(client, monkeypatch):
    c, main = client
    invocations = []
    def get_call(call_id, sensitive=False):
        invocations.append((call_id, sensitive))
        return {'id': call_id, 'CALLDATE': '2026-10-29'} if not sensitive else {
            'id': call_id, 'transcription': 'PRIVATE TEST TRANSCRIPT'
        }
    monkeypatch.setattr(main.database,'get_call',get_call)
    assert c.get('/dashboard/overview/5').status_code == 401
    user_id = main.store.create_user('readerwebmcp','another-long-password','reader',['calls:read'])
    raw, _ = main.store.create_session(user_id)
    c.cookies.set('panadan_session',raw)
    response=c.get('/dashboard/overview/5')
    assert response.status_code == 200
    assert response.json() == {'id':5,'CALLDATE':'2026-10-29'}
    assert response.headers['cache-control'] == 'no-store'
    assert invocations[-1] == (5,False)
    assert all(not sensitive for _,sensitive in invocations)

def test_browser_overview_denies_metrics_only_users(client):
    c, main = client
    user_id=main.store.create_user('onlymetricsweb','another-long-password','metrics',['metrics:read'])
    raw, _ = main.store.create_session(user_id)
    c.cookies.set('panadan_session',raw)
    assert c.get('/dashboard/overview/5').status_code == 403


def test_admin_activity_page_and_reporting_are_protected(client):
    c,main=client
    assert c.get('/dashboard/activity').status_code == 401
    assert c.get('/dashboard/activity/data').status_code == 401
    uid=main.store.create_user('activityreader','safe-reader-password-long','reader',['calls:read'])
    raw,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',raw)
    assert c.get('/dashboard/activity').status_code == 403
    assert c.get('/dashboard/activity/data').status_code == 403
    admin=main.store.verify_login('admin','a-long-safe-testing-password')
    token,_=main.store.create_session(admin)
    c.cookies.set('panadan_session',token)
    page=c.get('/dashboard/activity')
    assert page.status_code == 200
    assert 'فعالیت کاربران' in page.text
    data=c.get('/dashboard/activity/data?days=14')
    assert data.status_code == 200
    assert 'total' in data.json()
    assert data.headers['cache-control']=='no-store'
    assert c.get('/dashboard/activity/data?surface=invalid').status_code==400


def test_ai_transcripts_are_separately_permissioned_and_paged(client,monkeypatch):
    c,main=client
    calls=[]
    def excerpt(call_id,limit,offset):
        calls.append((call_id,limit,offset))
        return {'id':call_id,'transcription':'Hello 09121234567',
                'total_chars':12000}
    monkeypatch.setattr(main.database,'transcript_excerpt',excerpt)
    uid=main.store.create_user('ai_reader','ai-reader-password-long','analyst',
                               ['calls:read','metrics:read','mcp:use'])
    token,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',token)
    assert c.get('/dashboard/ai/transcript/8').status_code == 403
    assert not calls
    admin=main.store.verify_login('admin','a-long-safe-testing-password')
    raw,_=main.store.create_session(admin)
    c.cookies.set('panadan_session',raw)
    response=c.get('/dashboard/ai/transcript/8?offset=6000')
    assert response.status_code==200
    assert calls==[(8,6000,6000)]
    assert response.json()['has_more']
    assert response.json()['next_offset']==6017
    assert '09121234567' not in response.json()['text']
    logs=main.store.list_transcript_audit()
    assert logs[0]['surface']=='webmcp'
    assert logs[0]['call_id']==8


def test_operator_directory_filter_and_profile(client, monkeypatch):
    c,main=client
    admin=main.store.verify_login('admin','a-long-safe-testing-password')
    cookie,csrf=main.store.create_session(admin)
    c.cookies.set('panadan_session',cookie)
    assert c.get('/dashboard/operator?name=Test%20Op').status_code==200
    profile=c.get('/dashboard/operator?name=Test%20Op').text
    assert 'Test Op' in profile
    assert 'data-profile-operator="Test Op"' in profile
    directory=c.get('/dashboard/operators')
    assert directory.status_code==200
    assert 'کارشناسان و مقاصد' in directory.text
    assert 'نامشخص' in directory.text
    assert c.post('/dashboard/operators/assign',data={
        'csrf':'wrong','name':'Test Op','destination':'مشهد','team':'غرب آسیا'
    }).status_code==403
    response=c.post('/dashboard/operators/assign',data={
        'csrf':csrf,'name':'Test Op','destination':'مشهد','team':'غرب آسیا'
    },follow_redirects=False)
    assert response.status_code==303
    options=c.get('/dashboard/filter-options').json()
    assert {'value':'Test Op','label':'Test Op','destination':'مشهد','team':'غرب آسیا'} in options['operators']
    assert 'مشهد' in options['destinations']
    assert 'غرب آسیا' in options['teams']
    assert 'نامشخص' in options['destinations']
    seen={}
    def list_calls(*args,**kwargs):
        seen['args']=args
        seen['kwargs']=kwargs
        return []
    monkeypatch.setattr(main.database,'list_calls',list_calls)
    response=c.get('/dashboard/data?operator=Test%20Op&destination=مشهد')
    assert response.status_code==200
    assert seen['args'][:2] == (20, 0)
    assert seen['kwargs']['operator'] == 'Test Op'
    assert seen['kwargs']['any_operator_groups'] == [['Test Op']]
    assert c.get('/dashboard/data?destination=نامشخص').status_code==200
    flattened = seen['kwargs']['any_operator_groups'][0]
    assert '__unspecified__' in flattened
    assert 'Other Op' in flattened
    assert 'Test Op' not in flattened


def test_operator_assignment_admin_only_and_unknown_source_rejected(client):
    c,main=client
    uid=main.store.create_user('operator-reader','a-very-long-reader-password','reader',['calls:read'])
    token,csrf=main.store.create_session(uid)
    c.cookies.set('panadan_session',token)
    assert c.get('/dashboard/operators').status_code==200
    assert c.post('/dashboard/operators/assign',data={
        'name':'Test Op','team':'A','destination':'B','csrf':csrf
    }).status_code==403
    admin=main.store.verify_login('admin','a-long-safe-testing-password')
    token,csrf=main.store.create_session(admin)
    c.cookies.set('panadan_session',token)
    assert c.post('/dashboard/operators/assign',data={
        'name':'Not from database','team':'A','destination':'B','csrf':csrf
    }).status_code==400


def test_operator_rest_filter_retains_raw_values(client,monkeypatch):
    c,main=client
    uid=main.store.create_user('api_operator','another-long-password','analyst',
                               ['calls:read','metrics:read'])
    _,token=main.store.create_token('api operator','api:read',30,uid)
    seen={}
    def spy_list(*args,**kwargs):
        seen.update(kwargs)
        return []
    monkeypatch.setattr(main.database,'list_calls',spy_list)
    res=c.get('/api/v1/calls?operator=Test%20Op',headers={'Authorization':'Bearer '+token})
    assert res.status_code==200
    assert seen['operator']=='Test Op'
    assert seen['operator_names'] is None


def test_admin_templates_keep_login_ltr_and_user_editing_collapsed(client):
    c, main = client
    login = c.get('/login').text
    assert 'name="username" dir="ltr"' in login
    assert 'name="password" dir="ltr"' in login
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    users = c.get('/dashboard/users')
    assert users.status_code == 200
    assert 'class="user-card-summary"' in users.text
    assert 'class="user-edit-form"' in users.text
    assert 'class="token-form"' not in users.text
    activity = c.get('/dashboard/activity')
    assert activity.status_code == 200
    assert 'زمان (تهران)' in activity.text
    assert 'class="activity-col-duration"' in activity.text
    dashboard = c.get('/dashboard')
    assert dashboard.status_code == 200
    assert 'class="filters report-filters"' in dashboard.text


def test_favicon_and_voice_unit_are_available(client):
    c, _ = client
    icon = c.get('/static/favicon.svg')
    assert icon.status_code == 200
    assert 'image/svg+xml' in icon.headers['content-type']
    assert 'Panadan' in icon.text
    html = c.get('/login').text
    assert '/static/favicon.svg' in html
    templates = Path('templates')
    for name in (
        'login.html', 'dashboard.html', 'operators.html', 'tokens.html',
        'api.html', 'oauth.html', 'connect.html', 'users.html', 'activity.html'
    ):
        assert 'rel="icon" type="image/svg+xml"' in (templates / name).read_text()
    assert 'میانگین مدت صوت' in (templates / 'dashboard.html').read_text()
    assert 'ارزش معامله (تأییدنشده)' in Path('static/app.js').read_text()


def test_sales_ai_score_label_and_metric_coverage(client):
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    html = c.get('/dashboard')
    assert html.status_code == 200
    assert 'id="metric-score-coverage"' in html.text
    assert 'امتیاز احتمال فروش' in html.text
    stats = c.get('/dashboard/metrics')
    assert stats.status_code == 200
    assert stats.json()['scored_calls'] == 1
    assert stats.json()['avg_ai_score'] == 10
    assert 'امتیاز ثبت‌شده: ' not in Path('static/app.js').read_text()
    assert 'ثبت نشده' in Path('static/app.js').read_text()


def test_customer_phone_only_readable_with_sensitive_permission(client, monkeypatch):
    c, main = client
    calls = []
    def fake_get_call(call_id, sensitive=False):
        calls.append((call_id, sensitive))
        public = {'id': call_id, 'CALLDATE': '2026-10-29'}
        if sensitive:
            return {**public, 'customertell': '09121234567',
                    'customername': 'Synthetic Customer'}
        return public
    monkeypatch.setattr(main.database, 'get_call', fake_get_call)

    reader = main.store.create_user('call-reader-phone', 'reader-long-safe-password',
                                    'reader', ['calls:read'])
    cookie, _ = main.store.create_session(reader)
    c.cookies.set('panadan_session', cookie)
    response = c.get('/dashboard/data/5')
    assert response.status_code == 200
    assert 'customertell' not in response.json()
    assert calls[-1] == (5, False)

    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    response = c.get('/dashboard/data/5')
    assert response.status_code == 200
    assert response.json()['customertell'] == '09121234567'
    assert calls[-1] == (5, True)
    assert 'customertell' not in c.get('/dashboard/overview/5').json()
    assert calls[-1] == (5, False)
    assert "'customertell'" in Path('server/database.py').read_text()
    assert "dialablePhone(val)" in Path('static/app.js').read_text()


def test_token_datetime_rtl_order_and_utc_semantics(client):
    """Clock renders before date (right to left), without changing UTC storage."""
    import re
    from datetime import datetime, timezone
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    main.store.create_token('datetime-rtl-test', 'api:read', 7, admin)
    page = c.get('/dashboard/tokens')
    assert page.status_code == 200
    token_time = re.search(
        r'<time class="datetime-inline token-datetime"[^>]*>(.*?)</time>',
        page.text,
    )
    assert token_time is not None
    rendered = token_time.group(1)
    assert rendered.index('class="datetime-clock"') < rendered.index('class="datetime-date"')
    assert 'class="datetime-zone">UTC</span>' in rendered

    epoch = int(datetime(2026, 10, 29, 4, 39, tzinfo=timezone.utc).timestamp())
    assert main.templates.env.filters['date_time_clock'](epoch) == '04:39'
    assert main.templates.env.filters['date_time_day'](epoch) == '2026-10-29'
    assert main.templates.env.filters['date_time_iso'](epoch).endswith('+00:00')
    assert main.templates.env.filters['date_time_clock'](None) == '—'


def test_multi_value_report_filters_are_or_and_match_metrics(client, monkeypatch):
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    main.store.set_operator_assignment('Test Op', 'مشهد', 'غرب آسیا')
    calls, metrics = [], []
    def fake_list(*args, **kwargs):
        calls.append((args, kwargs))
        return []
    def fake_stats(*args, **kwargs):
        metrics.append((args, kwargs))
        return {'total': 0, 'sold_out': 0, 'scored_calls': 0,
                'avg_ai_score': None, 'avg_voice_length': None}
    monkeypatch.setattr(main.database, 'list_calls', fake_list)
    monkeypatch.setattr(main.database, 'stats', fake_stats)
    qs = ('?after=2026-10-01&operators=Test%20Op&operators=Other%20Op'
          '&direction=Incoming&direction=Outgoing'
          '&destination=مشهد&team=غرب%20آسیا&state=Unchecked&state=SoldOut')
    assert c.get('/dashboard/data' + qs).status_code == 200
    args, kw = calls[-1]
    assert args[2].isoformat() == '2026-10-01'
    assert kw['operator'] is None
    assert kw['filter_mode'] == 'any'
    assert kw['selected_facets']['operators'] == ['Test Op','Other Op']
    assert kw['selected_facets']['directions'] == ['Incoming','Outgoing']
    assert kw['selected_facets']['states'] == ['Unchecked','SoldOut']
    assert kw['any_operator_groups'] == [['Test Op'], ['Test Op']]
    assert c.get('/dashboard/metrics' + qs).status_code == 200
    _, metric_kw = metrics[-1]
    assert metric_kw['filter_mode'] == 'any'
    assert metric_kw['selected_facets'] == kw['selected_facets']
    assert metric_kw['any_operator_groups'] == kw['any_operator_groups']
    assert c.get('/dashboard/filter-options').json()['directions'] == ['Incoming','Outgoing']
    # Unknown/overlong selection lists are never allowed into SQL.
    assert c.get('/dashboard/data?'+'&'.join('state=S'+str(i) for i in range(21))).status_code == 400


def test_multi_filter_template_has_no_logic_switch(client):
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    page = c.get('/dashboard')
    assert page.status_code == 200
    assert 'فیلتر زمان ثبت (اختیاری)' not in page.text
    assert 'id="created_after-doran"' not in page.text
    for name in ('operator','destination','team','call_type','state','direction'):
        assert f'<select id="{name}" multiple data-multi' in page.text
    assert 'name="filter_mode"' not in page.text
    profile = c.get('/dashboard/operator?name=Test%20Op')
    assert profile.status_code == 200
    assert 'id="operator"' not in profile.text
    assert '<select id="state" multiple data-multi' in profile.text


def test_sticky_navigation_logout_available_on_all_admin_pages(client):
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    for page in ['/dashboard','/dashboard/activity','/dashboard/connect',
                 '/dashboard/tokens','/dashboard/users','/dashboard/operators',
                 '/dashboard/api','/dashboard/oauth']:
        response = c.get(page)
        assert response.status_code == 200, page
        assert 'action="/logout"' in response.text, page
    css = __import__('pathlib').Path('static/style.css').read_text()
    assert '.shell > .sidebar{' in css
    assert 'position:sticky;top:0' in css
    assert '.calls-panel tbody tr{' in css


def test_reporting_503_logs_only_safe_error_class_and_sqlstate(client, monkeypatch, caplog):
    """All dashboard data requests retain a safe HTTP response and sanitized log."""
    import logging
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)

    class SyntheticBackendFailure(Exception):
        sqlstate = '08006'
        def __str__(self):
            return 'db host 192.0.2.10 password=SECRET customer=09120000000'

    def failed_query(*args, **kwargs):
        raise SyntheticBackendFailure()
    monkeypatch.setattr(main.database, 'list_calls', failed_query)
    monkeypatch.setattr(main.database, 'stats', failed_query)
    monkeypatch.setattr(main.database, 'operators', failed_query)

    with caplog.at_level(logging.WARNING, logger='panadan.reporting'):
        for endpoint in ('/dashboard/data', '/dashboard/metrics',
                         '/dashboard/filter-options'):
            response = c.get(endpoint)
            assert response.status_code == 503
            assert response.json()['detail'] == 'Reporting database unavailable or query timed out'
            assert 'SECRET' not in response.text
        messages = [record.getMessage() for record in caplog.records
                    if record.name == 'panadan.reporting']
    assert len(messages) == 3
    assert all('SyntheticBackendFailure' in message and 'SQLSTATE=08006' in message
               for message in messages)
    assert all('192.0.2.10' not in message and 'SECRET' not in message
               and '09120000000' not in message
               for message in messages)


def test_reporting_sqlstate_logging_rejects_untrusted_code(client, caplog):
    import logging
    _, main = client
    class SecretError(Exception):
        sqlstate = '08006 password=PRIVATE'
        def __str__(self):
            return 'unsafe credentials and private customer data'
    with caplog.at_level(logging.WARNING, logger='panadan.reporting'):
        with pytest.raises(Exception) as error:
            main.json_failure(SecretError())
    assert getattr(error.value, 'status_code', None) == 503
    messages = [record.getMessage() for record in caplog.records
                if record.name == 'panadan.reporting']
    assert messages == ['Reporting backend failed type=SecretError SQLSTATE=unknown']
    assert 'PRIVATE' not in str(messages)


def test_dashboard_read_only_retry_recovers_from_one_transient_connection_error(client, monkeypatch):
    """A single broken reporting connection does not make the report 503."""
    import psycopg
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    calls = []
    def flaky_report(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise psycopg.OperationalError('private connection failure')
        return [{'id': 42, 'CALLDATE': '2026-10-31'}]
    monkeypatch.setattr(main.database, 'list_calls', flaky_report)
    response = c.get('/dashboard/data?after=2026-10-01&state=Unchecked')
    assert response.status_code == 200
    assert response.json()['items'][0]['id'] == 42
    assert len(calls) == 2
    assert calls[0] == calls[1]


def test_dashboard_does_not_retry_invalid_sql_or_validation_errors(client, monkeypatch):
    import psycopg
    c, main = client
    admin = main.store.verify_login('admin', 'a-long-safe-testing-password')
    cookie, _ = main.store.create_session(admin)
    c.cookies.set('panadan_session', cookie)
    calls = []
    def broken_report(*args, **kwargs):
        calls.append(True)
        raise psycopg.errors.UndefinedColumn('column unavailable')
    monkeypatch.setattr(main.database, 'stats', broken_report)
    response = c.get('/dashboard/metrics')
    assert response.status_code == 503
    assert len(calls) == 1
    assert c.get('/dashboard/data?after=not-a-date').status_code == 422

def test_mirror_health_is_admin_only_and_does_not_expose_customer_data(client, monkeypatch):
    c, main = client
    observed = []
    fake = {
        "state": "catching_up", "records": 97038, "revisions": 98719,
        "pages": 58, "lag_seconds": 7200,
        "completed_through": "2026-11-09T05:56:46+00:00",
        "last_processed": "2026-11-09T06:00:00+00:00",
        "window_upper": "2026-11-09T08:00:00+00:00",
        "last_commit": "2026-11-09T06:05:24Z",
        "generated_at": "2026-11-09T06:06:00Z",
        "vpn_healthy": True, "timer_active": True,
        "disk_free_bytes": 6800000000, "source_enabled": False,
        "detail": "telemetry_only",
    }

    def load():
        observed.append(True)
        return fake

    monkeypatch.setattr(main.mirror_health, "load_admin_mirror_health", load)
    assert c.get("/dashboard/mirror-health").status_code == 401
    assert not observed

    user_id = main.store.create_user(
        "mirror_reader", "another-long-password", "reader", ["calls:read"])
    raw, _ = main.store.create_session(user_id)
    c.cookies.set("panadan_session", raw)
    assert c.get("/dashboard/mirror-health").status_code == 403
    assert "mirror-health-panel" not in c.get("/dashboard").text
    assert not observed

    admin_id = main.store.verify_login(
        "admin", "a-long-safe-testing-password")
    raw, _ = main.store.create_session(admin_id)
    c.cookies.set("panadan_session", raw)
    page = c.get("/dashboard")
    assert page.status_code == 200
    assert "mirror-health-panel" in page.text
    assert "/static/mirror-health.js" in page.text
    assert c.get("/dashboard/operator?name=Test%20Op").status_code == 200
    assert "mirror-health-panel" not in c.get(
        "/dashboard/operator?name=Test%20Op").text

    result = c.get("/dashboard/mirror-health")
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json() == fake
    assert observed == [True]
    assert "customername" not in result.text
    assert "transcription" not in result.text
