"""Nimbus services: the customer's servers and container apps, and the actions the agent carries out on them
(built outside Genesis, like the web portal; see the open-issues register).

- nimbus_services: one row per service of a signed-in customer (tenant row-level security). A change takes a
  few seconds, as on a real cloud: an action sets the in-between status (stopping) with the status it settles
  to (stopped) and when; every read shows the settled status once that time has passed, so nothing has to run
  in the background.
- service_actions: what the agent offered (ACT-nnnnn) and, once the customer confirmed it, what was done. The
  Services tab's activity is the done ones.
- understand(): in code, never a model: an action word (stop, start, restart, scale) and one of the customer's
  own services named in the message. Several matches or a missing replica count -> a question; nothing named
  -> not a service request.
- nimbus_services.run_action: the audited write tool (tools.execution.Executor) that carries out a confirmed
  offer. Like support_desk.raise_ticket, its only argument is the offer's number, the on-behalf-of token says
  whose it is, a repeat changes nothing more, and no model or specialist is offered it (CUSTOMER_ACTION).
"""

import re
from datetime import datetime

from pydantic import BaseModel

from channels.identity.tiers import Tier
from data.migrate import psql
from hitl.queues import Refused, context
from tools.desk import CUSTOMER_ACTION
from tools.execution import System, ToolFailure, current
from tools.schemas import arg

SCHEMA_NAME = "nimbus_0002_services.sql"
SCHEMA = """
CREATE TABLE nimbus_services (
  tenant_id    text NOT NULL REFERENCES tenants (id),
  principal_id text NOT NULL,
  service_id   text NOT NULL,
  name         text NOT NULL,
  kind         text NOT NULL CHECK (kind IN ('server', 'app')),
  region       text NOT NULL,
  status       text NOT NULL,
  settles_to   text,
  settles_at   timestamptz,
  replicas     integer CHECK (replicas BETWEEN 1 AND 10),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, service_id),
  UNIQUE (tenant_id, principal_id, name)
);
CREATE TABLE service_actions (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id       text NOT NULL REFERENCES tenants (id),
  principal_id    text NOT NULL,
  conversation_id text NOT NULL,
  proposal_key    text NOT NULL,
  service_id      text NOT NULL,
  action          text NOT NULL CHECK (action IN ('stop', 'start', 'restart', 'scale')),
  replicas        integer CHECK (replicas BETWEEN 1 AND 10),
  status          text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'done')),
  expires_at      timestamptz NOT NULL DEFAULT now() + interval '24 hours',
  created_at      timestamptz NOT NULL DEFAULT now(),
  done_at         timestamptz,
  UNIQUE (tenant_id, conversation_id, proposal_key)
);
CREATE INDEX service_actions_owner ON service_actions (tenant_id, principal_id, status, done_at);
""" + "".join(f"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON {t}
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE {t} OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE ON {t} TO app_runtime;
""" for t in ("nimbus_services", "service_actions"))

AUDIENCE = "status-tools"   # T1: an email-code customer may run these (reversible) actions
RUN = "nimbus_services.run_action"
SYSTEMS = {"nimbus_services": System("nimbus_services", frozenset(), "obo", AUDIENCE, idempotent_writes=True)}
SETTLE = "8 seconds"        # how long an action takes to settle
# action -> (kinds it applies to, the status it needs, the status while it runs, the status it settles to)
ACTIONS = {"stop": ({"server"}, "running", "stopping", "stopped"),
           "start": ({"server"}, "stopped", "starting", "running"),
           "restart": ({"server", "app"}, "running", "restarting", "running"),
           "scale": ({"app"}, "running", "scaling", "running")}
LABELS = {"stop": "Stop", "start": "Start", "restart": "Restart", "scale": "Scale"}
KINDS = {"server": "server", "app": "container app"}
STATUS = "CASE WHEN s.settles_at <= now() THEN s.settles_to ELSE s.status END"
SERVICE = (f"SELECT s.service_id, s.name, s.kind, s.region, {STATUS}, s.replicas, s.updated_at "
           "FROM nimbus_services s")
FIELDS = ("service_id", "name", "kind", "region", "status", "replicas", "updated_at")

VERB = re.compile(r"\b(?P<restart>restart|reboot|bounce)\b"
                  r"|\b(?P<stop>stop|shut ?down|close|turn off|power off|halt)\b"
                  r"|\b(?P<start>start|boot|turn on|power on|bring up)\b|\b(?P<scale>scale)\b",
                  re.IGNORECASE)
HOW_TO = re.compile(r"\bhow (do|can|would|to)\b|\bwhat happens\b", re.IGNORECASE)
REPLICAS = re.compile(r"\bto\s+(\d{1,2})\b|\b(\d{1,2})\s+(?:replicas?|instances?|pods?|copies)\b",
                      re.IGNORECASE)
WORD = re.compile(r"[a-z]{4,}")
GENERIC = {"server", "servers", "service", "services", "container", "containers"}


class RunAction(BaseModel):
    proposal: str = arg(False, personal=False, pattern=r"^ACT-[0-9]{5,}$")  # an offer the agent issued


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def number(action_id):
    return f"ACT-{action_id:05d}"


def number_id(text):
    """ACT-00042 -> 42; anything else -> None."""
    digits = str(text).removeprefix("ACT-")
    return int(digits) if str(text).startswith("ACT-") and digits.isdigit() else None


def _json(row):
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in zip(FIELDS, row, strict=True)}


def services(connect, tenant_id, principal_id):
    """The customer's services with their settled status, servers first."""
    with connect() as conn, conn.transaction():
        context(conn, tenant_id)
        rows = conn.execute(f"{SERVICE} WHERE s.tenant_id = %s AND s.principal_id = %s ORDER BY s.kind DESC, "
                            "s.name", (tenant_id, principal_id)).fetchall()
    return [_json(row) for row in rows]


def service(connect, tenant_id, principal_id, service_id):
    with connect() as conn, conn.transaction():
        context(conn, tenant_id)
        row = conn.execute(f"{SERVICE} WHERE s.tenant_id = %s AND s.principal_id = %s AND s.service_id = %s",
                           (tenant_id, principal_id, service_id)).fetchone()
    return _json(row) if row else None


def activity(connect, tenant_id, principal_id, limit=20):
    """What the agent did on the customer's services, newest first."""
    with connect() as conn, conn.transaction():
        context(conn, tenant_id)
        rows = conn.execute(
            "SELECT a.id, s.name, a.action, a.replicas, a.conversation_id, a.done_at FROM service_actions a "
            "JOIN nimbus_services s ON s.tenant_id = a.tenant_id AND s.service_id = a.service_id "
            "WHERE a.tenant_id = %s AND a.principal_id = %s AND a.status = 'done' "
            "ORDER BY a.done_at DESC LIMIT %s", (tenant_id, principal_id, limit)).fetchall()
    return [{"action_id": number(i), "service": name, "action": action, "replicas": replicas,
             "conversation_id": conversation, "at": at.isoformat()}
            for i, name, action, replicas, conversation, at in rows]


def understand(text, own):
    """What a message asks of the customer's own services (`own`, from services()): None when it is not a
    request to act on one, {"reply": question} when something is unclear, else
    {"service": row, "action": name, "replicas": n or None}."""
    verb = VERB.search(text)
    if not verb or HOW_TO.search(text):
        return None
    action = verb.lastgroup
    low = text.lower()
    named = [s for s in own if s["name"].lower() in low]
    if not named:
        words = set(WORD.findall(low)) - GENERIC
        named = [s for s in own if words & (set(WORD.findall(s["name"].lower())) - GENERIC)]
    if not named:
        return None
    if len(named) > 1:
        return {"reply": "Which one do you mean: " + ", ".join(s["name"] for s in named) + "?"}
    target = named[0]
    kinds, needs, _, _ = ACTIONS[action]
    if target["kind"] not in kinds:
        can = " or ".join(a for a, spec in ACTIONS.items() if target["kind"] in spec[0])
        return {"reply": f"{target['name']} is a {KINDS[target['kind']]}: I can {can} it, not {action} it."}
    if target["status"] != needs:
        return {"reply": f"{target['name']} is {target['status']} right now, so there is nothing to "
                         f"{action}."}
    replicas = None
    if action == "scale":
        found = REPLICAS.search(text)
        replicas = int(found.group(1) or found.group(2)) if found else None
        if replicas is None or not 1 <= replicas <= 10:
            return {"reply": f"How many replicas should {target['name']} run? Between 1 and 10; it runs "
                             f"{target['replicas']} now."}
    return {"service": target, "action": action, "replicas": replicas}


def propose(connect, tenant_id, principal_id, conversation_id, turn_id, service_id, action, replicas=None):
    """The offer for this turn (the same one again when the turn is retried): its ACT number."""
    with connect() as conn, conn.transaction():
        context(conn, tenant_id)
        conn.execute("INSERT INTO service_actions (tenant_id, principal_id, conversation_id, proposal_key, "
                     "service_id, action, replicas) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                     "ON CONFLICT DO NOTHING",
                     (tenant_id, principal_id, conversation_id, turn_id, service_id, action, replicas))
        row = conn.execute("SELECT id FROM service_actions WHERE tenant_id = %s AND conversation_id = %s AND "
                           "proposal_key = %s", (tenant_id, conversation_id, turn_id)).fetchone()
    return number(row[0])


def confirm(connect, tenant_id, principal_id, action_id):
    """Carry out the customer's offer once -> (action, service after it). A repeat returns the service as it
    is; someone else's, an unknown or an expired offer, or a service no longer in the status the action needs,
    is Refused and changes nothing."""
    with connect() as conn, conn.transaction():
        context(conn, tenant_id)
        offer = conn.execute("SELECT service_id, action, replicas, status, now() > expires_at "
                             "FROM service_actions WHERE tenant_id = %s AND principal_id = %s AND id = %s "
                             "FOR UPDATE", (tenant_id, principal_id, action_id)).fetchone()
        if offer is None:
            raise Refused("no such offer")
        service_id, action, replicas, status, expired = offer
        where = "WHERE s.tenant_id = %s AND s.principal_id = %s AND s.service_id = %s"
        if status == "done":
            return action, _json(conn.execute(f"{SERVICE} {where}", (tenant_id, principal_id, service_id))
                                 .fetchone())
        if expired:
            raise Refused("this offer has expired")
        conn.execute(f"SELECT 1 FROM nimbus_services s {where} FOR UPDATE",
                     (tenant_id, principal_id, service_id))
        now = _json(conn.execute(f"{SERVICE} {where}", (tenant_id, principal_id, service_id)).fetchone())
        _, needs, running, settled = ACTIONS[action]
        if now["status"] != needs:
            raise Refused(f"the service is {now['status']} now")
        conn.execute("UPDATE nimbus_services SET status = %s, settles_to = %s, "
                     f"settles_at = now() + interval '{SETTLE}', replicas = coalesce(%s, replicas), "
                     "updated_at = now() WHERE tenant_id = %s AND service_id = %s",
                     (running, settled, replicas, tenant_id, service_id))
        conn.execute("UPDATE service_actions SET status = 'done', done_at = now() WHERE id = %s",
                     (action_id,))
        return action, _json(conn.execute(f"{SERVICE} {where}", (tenant_id, principal_id, service_id))
                             .fetchone())


def register(registry, connect, identity):
    """Add nimbus_services.run_action to `registry` (before it is frozen)."""
    def run_action(args):
        claims = identity.verify_obo(current().credential, AUDIENCE)
        try:
            action, after = confirm(connect, claims["tid"], claims["sub"], number_id(args.proposal))
        except Refused as refused:
            raise ToolFailure("REJECTED", str(refused)) from refused
        return {"action": action, "service": after}

    registry.tool(RUN, args=RunAction, description="Carry out the service action the customer has confirmed",
                  risk="low_risk_write", stages={CUSTOMER_ACTION}, min_tier=Tier.T1_VERIFIED,
                  author="claude")(run_action)  # reviewed_by: set when a person reviews it
    return registry


# What the customer sees in the chat (runtime.TurnLoop)

NOT_DONE = ("I could not make that change: the offer has expired, is not yours, or the service has changed "
            "since. Its current state is under Services; tell me what you need and I will set it up again.")
SIGN_IN_AGAIN = ("Please sign in with your email code again to confirm the change; your offer is kept for "
                 "a day.")
SIGN_IN_CARD = {"kind": "sign_in", "title": "Sign in to confirm the change",
                "actions": [{"type": "sign_in", "label": "Sign in with your email"}]}


def what(target, action, replicas):
    scale = f" to {replicas} replicas" if action == "scale" else ""
    return f"{action} the {KINDS[target['kind']]} {target['name']}{scale}"


def offer_card(offer, target, action, replicas):
    return {"kind": "service_action_proposal", "title": f"{LABELS[action]} {target['name']}?",
            "action_id": offer, "action": action, "replicas": replicas, "service": target["name"],
            "service_kind": target["kind"], "region": target["region"], "status": target["status"],
            "actions": [{"type": "confirm_action", "proposal": offer,
                         "label": f"{LABELS[action]} {KINDS[target['kind']]}"}]}


def offer_reply(target, action, replicas):
    return (f"I can {what(target, action, replicas)} ({target['region']}, {target['status']} now). Nothing "
            f"has changed yet: use {LABELS[action]} {KINDS[target['kind']]} to confirm, and you can follow "
            "it under Services.")


def done_card(action, after):
    return {"kind": "service", "title": f"{after['name']} is {after['status']}", "action": action,
            "service": after["name"], "service_kind": after["kind"], "region": after["region"],
            "status": after["status"], "replicas": after["replicas"]}


def done_reply(action, after):
    settled = ACTIONS[action][3]
    if after["status"] == settled:
        return f"{after['name']} is {settled}. You can see it under Services."
    return (f"{after['name']} is {after['status']} now and will be {settled} in a few seconds. You can "
            "follow it under Services.")


def seed(connect, tenant_id, principal_id, region="eu-central-1"):
    """Demo services for one customer; running it again changes nothing."""
    short = principal_id.split("@", 1)[0][:12]
    rows = [("payments-api-01", "server", "running", None), ("batch-worker-02", "server", "running", None),
            ("staging-web-01", "server", "stopped", None), ("checkout-worker", "app", "running", 2),
            ("notifications", "app", "running", 1)]
    with connect() as conn, conn.transaction():
        context(conn, tenant_id)
        for n, (name, kind, status, replicas) in enumerate(rows, 1):
            conn.execute("INSERT INTO nimbus_services (tenant_id, principal_id, service_id, name, kind, "
                         "region, status, replicas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                         "ON CONFLICT DO NOTHING",
                         (tenant_id, principal_id, f"svc-{short}-{n}", name, kind, region, status, replicas))
