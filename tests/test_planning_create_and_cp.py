from app.models import db, User, Project, Phase, Feature, Item
from datetime import date

def login(client):
    return client.post('/login', data={'username':'tester','password':'pass'}, follow_redirects=True)

def setup_base(app):
    with app.app_context():
        u = User.query.filter_by(username='tester').first()
        proj = Project(title='CPProj', owner_id=u.id)
        db.session.add(proj); db.session.commit()
        return proj.id

def test_create_parts_and_cp(app, client):
    login(client)
    pid = setup_base(app)
    # set project
    client.post('/set_project', data={'project-id':pid})
    # create phase
    ph_resp = client.post('/create_part', data={'part-type':'phase','part-title':'Phase A','part-start':date.today().isoformat(),'duration':'3'})
    assert ph_resp.status_code in (200,302)
    # retrieve created phase id from DB
    with app.app_context():
        ph_id = Phase.query.filter_by(title='Phase A').first().id
    # create feature depending on none
    ft_resp = client.post('/create_part', data={'part-type':'feature','part-title':'Feature A','phase-id':str(ph_id),'part-start':date.today().isoformat(),'duration':'2'})
    assert ft_resp.status_code in (200,302)
    # get feature id
    with app.app_context():
        ft_id = Feature.query.filter_by(title='Feature A').first().id
    # create item under feature, depending on none
    it_resp = client.post('/create_part', data={'part-type':'item','part-title':'Item A','feature-id':str(ft_id),'part-start':date.today().isoformat(),'duration':'2'})
    assert it_resp.status_code in (200,302)
    # create second item depending on first (assume first got id 1 in fresh DB)
    it2 = client.post('/create_part', data={'part-type':'item','part-title':'Item B','feature-id':str(ft_id),'part-start':date.today().isoformat(),'duration':'2','part-dependencies':'item-1'})
    assert it2.status_code in (200,302)
    # fetch index and ensure critical path JSON present
    idx = client.get('/')
    assert idx.status_code==200
    assert b'Critical Path:' in idx.data
