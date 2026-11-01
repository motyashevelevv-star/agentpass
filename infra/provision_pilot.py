"""Offline operator onboarding; no public registration or default pilot password."""
import argparse
import getpass
from sqlalchemy import select
from agentpass.config import settings
from agentpass.db import SessionLocal,uid
from agentpass.models import User,Organization,Member
from agentpass.security import password_hash


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email',required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--organization',required=True)
    parser.add_argument('--platform-admin',action='store_true')
    args=parser.parse_args()
    if settings().environment!='pilot':
        raise SystemExit('Only ENVIRONMENT=pilot is accepted; configure a new database first')
    email=args.email.strip().lower()
    if '@' not in email or email.endswith('@agentpass.local'):
        raise SystemExit('Use a verified corporate email, not a demo identity')
    password=getpass.getpass('New password (16+ characters): ')
    if len(password)<16 or len(password)>128 or password=='AgentPass-demo-2026!':
        raise SystemExit('Password rejected')
    if getpass.getpass('Repeat password: ')!=password:
        raise SystemExit('Passwords do not match')
    with SessionLocal.begin() as db:
        if db.scalar(select(User).where(User.email==email)):
            raise SystemExit('Account exists; refusing to overwrite credentials or MFA')
        user=User(id=uid(),email=email,name=args.name,password_hash=password_hash(password),platform_admin=args.platform_admin)
        org=Organization(id=uid(),name=args.organization)
        db.add_all([user,org]);db.flush()
        db.add(Member(user_id=user.id,organization_id=org.id,role='owner'))
    print('Created operator-approved account. Enroll MFA in Security before sensitive operations.')


if __name__=='__main__':main()
