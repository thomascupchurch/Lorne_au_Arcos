from app.models import DraftPart, Project, Phase, Feature, Item

def login(client):
    client.post('/login', data={'username':'tester','password':'pass'}, follow_redirects=True)

def create_project(client, title='ProjAuto'):
    client.post('/create_project', data={'project-title': title}, follow_redirects=True)

def test_auto_promote_phase(app, client):
    login(client)
    create_project(client)
    # create draft without type
    r = client.post('/create_draft_part', data={'draft-title':'Draft A'})
    assert r.status_code == 200
    d_id = r.get_json()['draft']['id']
    # promote as phase (empty drop)
    pr = client.post('/promote_draft_auto', json={'draft_id': d_id, 'inferred_type':'phase', 'start':'2025-01-10', 'duration':5})
    assert pr.status_code == 200
    data = pr.get_json()
    assert data['created']['type'] == 'phase'
    assert data['created']['duration'] == 5
    assert d_id == int(data['removed_draft_id'])
    assert 'critical_path' in data
    with app.app_context():
        assert DraftPart.query.get(d_id) is None
        assert Phase.query.count() == 1


def test_auto_promote_feature(app, client):
    login(client)
    create_project(client)
    # Create a phase to attach feature
    client.post('/create_part', data={'part-type':'phase','part-title':'P1','part-start':'2025-01-01','part-duration':'4'})
    # Draft
    r = client.post('/create_draft_part', data={'draft-title':'Draft Feature'})
    d_id = r.get_json()['draft']['id']
    from app.models import Phase as Ph
    with app.app_context():
        ph_id = Ph.query.first().id
    pr = client.post('/promote_draft_auto', json={'draft_id':d_id,'inferred_type':'feature','start':'2025-01-05','duration':3,'phase_id':ph_id})
    assert pr.status_code == 200
    data = pr.get_json()
    assert data['created']['type']=='feature'
    assert data['created']['duration']==3

def test_auto_promote_item(app, client):
    login(client)
    create_project(client)
    # Phase + Feature
    client.post('/create_part', data={'part-type':'phase','part-title':'P1','part-start':'2025-01-01','part-duration':'4'})
    from app.models import Phase as Ph
    with app.app_context(): ph_id = Ph.query.first().id
    client.post('/create_part', data={'part-type':'feature','part-title':'F1','part-start':'2025-01-02','duration':'2','phase-id':ph_id})
    with app.app_context(): feature_id = Feature.query.first().id
    r = client.post('/create_draft_part', data={'draft-title':'Draft Item'})
    d_id = r.get_json()['draft']['id']
    pr = client.post('/promote_draft_auto', json={'draft_id':d_id,'inferred_type':'item','start':'2025-01-03','duration':1,'feature_id':feature_id})
    assert pr.status_code == 200
    assert pr.get_json()['created']['type']=='item'


def test_conflict_type(app, client):
    login(client)
    create_project(client)
    # create draft with explicit type phase
    r = client.post('/create_draft_part', data={'draft-title':'Typed','draft-type':'phase'})
    d_id = r.get_json()['draft']['id']
    # attempt to promote as item -> should error
    pr = client.post('/promote_draft_auto', json={'draft_id':d_id,'inferred_type':'item','start':'2025-01-01','duration':2,'phase_id':123})
    assert pr.status_code == 400
    assert 'conflict' in pr.get_json()['error']


def test_missing_parent_error(app, client):
    login(client)
    create_project(client)
    r = client.post('/create_draft_part', data={'draft-title':'NeedsParent'})
    d_id = r.get_json()['draft']['id']
    # Try to promote item without feature_id
    pr = client.post('/promote_draft_auto', json={'draft_id':d_id,'inferred_type':'item','start':'2025-01-01','duration':2})
    assert pr.status_code == 400
    assert 'feature_id' in pr.get_json()['error']
