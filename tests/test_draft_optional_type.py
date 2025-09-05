from app.models import DraftPart

def test_create_draft_without_type(app, client):
    # login
    client.post('/login', data={'username':'tester','password':'pass'}, follow_redirects=True)
    # create project to set selected_project_id in session
    client.post('/create_project', data={'project-title':'Proj Draft'}, follow_redirects=True)
    # create draft without providing draft-type
    resp = client.post('/create_draft_part', data={'draft-title':'My Untyped Draft'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    draft = data['draft']
    assert draft['type'] is None
    assert draft['needs_type'] is True
    # confirm persisted in DB
    with app.app_context():
        stored = DraftPart.query.get(draft['id'])
        assert stored is not None and stored.part_type is None
