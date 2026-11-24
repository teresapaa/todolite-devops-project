"""Reset the database and add 20 demo users with todos.

Demo users get placeholder OIDC subjects, so nobody can sign in as them; they only
populate the admin area. Real accounts are created on the first Google sign-in.
Warning: this drops all tables, including real accounts."""
import random

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from app import create_app
from models import db, Todo, User

app = create_app()
random.seed(42)

with app.app_context():
    db.drop_all()
    db.create_all()
    for number in range(1, 21):
        user = User(oidc_issuer="seed", oidc_sub=f"demo{number}",
                    email=f"demo{number}@example.com", name=f"Demo {number}")
        db.session.add(user)
        db.session.flush()
        for index in range(random.randint(5, 10)):
            created = datetime.utcnow() - timedelta(days=random.randint(1, 14))
            completed = random.choice([False, False, True])
            db.session.add(Todo(
                user_id=user.id,
                title=f"Demo todo {index + 1} for {user.name}",
                priority=random.randint(1, 5),
                completed=completed,
                created_at=created,
                completed_at=(min(created + timedelta(days=random.randint(0, 10)), datetime.utcnow())
                              if completed else None),
            ))
    db.session.commit()
    print("Seeded 20 demo users with 5-10 todos each (they cannot sign in).")
