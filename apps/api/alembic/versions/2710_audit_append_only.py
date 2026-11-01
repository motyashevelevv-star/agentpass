"""Guard audit records against UPDATE and DELETE by ordinary application statements."""

from alembic import op

revision = "2710_audit_append_only"
down_revision = "1f5c0feec07e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION protect_audit_events() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'audit_events are append-only'; END; $$""")
    op.execute(
        "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION protect_audit_events()"
    )


def downgrade():
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION protect_audit_events()")
