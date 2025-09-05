from app.models import db, Project, Phase, Feature, Item, Image, User

def login(client):
    return client.post('/login', data={'username':'tester','password':'pass'}, follow_redirects=True)

def test_media_association_flow(app, client):
    login(client)
    from datetime import date
    with app.app_context():
        u = User.query.filter_by(username='tester').first()
        proj = Project(title='Proj A', owner_id=u.id)
        db.session.add(proj)
        db.session.commit()
        proj_id = proj.id
        phase = Phase(title='Phase 1', start_date=date.today(), duration=1, project_id=proj_id)
        db.session.add(phase)
        db.session.commit()
    feature = Feature(title='Feature 1', start_date=date.today(), duration=2, phase_id=phase.id)
    db.session.add(feature); db.session.commit()
    item = Item(title='Item 1', start_date=date.today(), duration=2, feature_id=feature.id)
    db.session.add(item); db.session.commit()
        img = Image(filename='f.png', project_id=proj_id)
        db.session.add(img)
        db.session.commit()
        iid = img.id
        phase_id = phase.id
    feature_id = feature.id; item_id = item.id
    # associate to phase
    r = client.post('/media/associate', json={'image_id':iid,'target_type':'phase','target_id':phase_id})
    assert r.status_code==200
    # associate to feature and item
    r2 = client.post('/media/associate', json={'image_id':iid,'target_type':'feature','target_id':feature_id})
    assert r2.status_code==200
    r3 = client.post('/media/associate', json={'image_id':iid,'target_type':'item','target_id':item_id})
    assert r3.status_code==200
    data = client.get(f'/media/links/{iid}').get_json()
    assert len(data['phases'])==1 and len(data['features'])==1 and len(data['items'])==1
    un = client.post('/media/unlink', json={'image_id':iid,'context_type':'feature','context_id':feature_id})
    assert un.status_code==200
    links2 = client.get(f'/media/links/{iid}').get_json()
    assert len(links2['features'])==0 and len(links2['phases'])==1 and len(links2['items'])==1
