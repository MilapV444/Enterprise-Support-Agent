# UA-ADP-02: Identity Assurance & Downstream Token Delegation (Tiered Identity + RFC 8693 On-Behalf-Of Delegation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-23
- **Deciders**: Architecture Team, Lead Security Architect, Identity & Access Management (IAM) Core
- **Component**: `[1] User & Application` (`Component [ 1 ]`)
- **Reasoning Source**: `checkpoint.md` §5 · Diagram: `LLD - [1] User & Application`
- **Decisions Covered**:
  - `UA-D3`: Identity Assurance — Tiered Assurance (`T0_ANON` $\to$ `T1_VERIFIED` $\to$ `T2_SSO`) with Step-Up Challenges
  - `UA-D4`: Downstream Identity — RFC 8693 Token Exchange (`sub` + `act` Claims) with T0 Read-Only Audience
  - `UA-D9`: Token Validity — 24-Hour User Access Token Lifespan (Fixing Session Expiry Variants)
- **Related Architectural Decision Points**:
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ta-adp-04--execution-credentials--isolation): Tool Execution Credentials *(Scoped Service Accounts & Agent-Side Checks)*
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-04--authorization--tool-permissions): Authorization & Tool Permissions *(RBAC & ABAC Envelopes)*
  - [`UA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-03-sessions-conversation-scope.md): Sessions & Conversation Scope *(12-Hour Absolute Session Cap)*

---

## 1. Context & Problem Statement

Enterprise AI support agents operate in a high-stakes security perimeter: they interface with unauthenticated web visitors seeking public product documentation while simultaneously possessing the operational capability to execute deep backend side-effects (e.g., retrieving customer invoices, resetting passwords, updating subscription seats, or altering cloud infrastructure configurations).

Historically, identity architectures for conversational systems have collapsed into two dangerous extremes:
1. **The Confused Deputy Vulnerability (Hardy, 1988)**: The agent authenticates to downstream systems (Salesforce, Stripe, AWS, internal APIs) using a static, highly privileged system service account, treating the user's conversational intent as authorization. Under indirect prompt injection or logic manipulation, an attacker tricks the agent into executing privileged actions beyond the end-user's true authorization boundaries.
2. **Aggressive Authentication Wall (High Customer Effort & Bounce)**: Forcing full enterprise Single Sign-On (SSO) before a user can ask a basic public documentation question introduces severe friction. Under **Customer Effort Score (CES)** analysis, mandatory login walls cause bounce rates exceeding 40% on top-of-funnel customer inquiries.
3. **Mid-Stream Token Expiration Desynchronization ($KK3$)**: Long-lived multi-turn sessions frequently outlive user OAuth2 access tokens (typically 1 hour), causing intermediate tool operations to fail mid-conversation and leaving support workflows in broken states.

### The Core Architectural Question
> **How does the system establish verifiable identity assurance across varying levels of user intent, and what precise cryptographic authority does the agent carry when invoking downstream enterprise services on behalf of the customer?**

---

## 2. Decision Framework & Theoretical Formulation

We ground our identity and authorization architecture in three theoretical pillars: **NIST Authenticator Assurance Levels (AAL)**, **Cryptographic Delegation & Saltzer-Schroeder Least Privilege**, and **Erlang A Customer Abandonment Economics**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             IDENTITY THEORETICAL PILLARS                                         │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: NIST SP 800-63B    │   Pillar B: Cryptographic      │   Pillar C: Customer Effort    │
│   Tiered Assurance & Step-Up   │   Delegation (RFC 8693 OBO)    │   Score & Abandonment Model    │
│                                │                                │                                │
│   • T0: Anonymous (AAL0)       │   • Eliminates Confused Deputy │   • Erlang A hazard rate       │
│   • T1: Verified OTP (AAL1)    │   • Actor claim: act = agent   │   • P(Abandon) = f(Friction)   │
│   • T2: Enterprise SSO (AAL2)  │   • Subject claim: sub = user  │   • Dynamic Step-Up Minimizes  │
│   • Action-Risk Step-Up Gate   │   • Audience-restricted scope  │     Friction while bounding Risk│
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: NIST SP 800-63B Tiered Assurance & Dynamic Step-Up

Following the **NIST SP 800-63B Digital Identity Guidelines**, identity verification is not binary; it is stratified into distinct Authenticator Assurance Levels (AAL):

$$\mathcal{T} = \{\text{T0}_{\text{Anon}}, \text{T1}_{\text{Verified}}, \text{T2}_{\text{SSO}}\}$$

1. **Tier 0: Anonymous (`T0_ANON`) [AAL0]**:
   - Zero credentials required. Ephemeral session UUID generated at client ingress.
   - Authorized Scope: Public knowledge base retrieval, documentation Q&A, and public product catalog navigation.
2. **Tier 1: Verified via Out-of-Band OTP (`T1_VERIFIED`) [AAL1]**:
   - One-Time Password (OTP) dispatched to verified email/SMS on file.
   - Authorized Scope: Low-risk read actions (e.g., viewing public ticket status, order tracking) and non-destructive case updates.
3. **Tier 2: Authenticated Enterprise SSO (`T2_SSO`) [AAL2]**:
   - Cryptographically signed OpenID Connect (OIDC) JWT / SAML 2.0 assertion via corporate Identity Provider (Okta, Azure AD, Auth0) with multi-factor authentication (MFA).
   - Authorized Scope: High-risk actions, PII disclosures, financial adjustments, and tenant configuration modifications.

#### Dynamic Step-Up Enforcement Invariant
When the agent's Intent & Acuity Engine (`ADP-01` / `ADP-05`) classifies an incoming intent as requiring assurance level $\mathcal{T}_{\text{required}} > \mathcal{T}_{\text{current}}$:

$$\text{Transition Condition: } \mathcal{T}_{\text{current}} < \mathcal{T}_{\text{required}} \implies \text{Emit Step-Up Challenge}$$

The orchestrator halts state transitions, emits an interactive authentication challenge card, and preserves conversation state. Execution resumes automatically upon verified credential receipt.

---

### Pillar B: Cryptographic Delegation & RFC 8693 Token Exchange

To permanently resolve the **Confused Deputy Problem (Hardy, 1988)** and adhere to the **Principle of Least Privilege (Saltzer & Schroeder, 1975)**, the agent runtime **never uses ambient master credentials**.

All downstream tool invocations leverage **OAuth 2.0 Token Exchange (RFC 8693)** to mint short-lived, audience-restricted On-Behalf-Of (OBO) JWTs.

#### The OBO Token Cryptographic Claims Structure
The downstream token carries explicit dual-identity claims:

$$\text{JWT Claims} = \begin{cases}
\texttt{iss}: & \text{"https://auth.enterprise.com"} \\
\texttt{sub}: & \text{PrincipalUUID (The end-user)} \\
\texttt{act}: & \{ \texttt{sub}: \text{"svc:enterprise-agent-runtime"} \} \quad (\textbf{Actor Claim}) \\
\texttt{aud}: & \text{"https://api.enterprise.com/billing"} \quad (\textbf{Target Audience}) \\
\texttt{tier}: & \text{"T2\_SSO"} \\
\texttt{exp}: & t_{\text{mint}} + 900\text{s} \quad (\textbf{Short-Lived: 15 Minutes})
\end{cases}$$

```
[End-User JWT] ──> [Security Token Service (STS)] ──> [RFC 8693 Exchange] ──> [Downstream API]
  (sub = sarah)              (Validates Claims)         (sub = sarah,              (Validates:
                                                         act = agent,              Can SARAH do this?
                                                         aud = billing_api)        Is AGENT allowed?)
```

#### The T0 Minimal Read-Only Token Rule (`UA-Q1 -> ii`)
Even anonymous users (`T0_ANON`) cannot invoke tools without an identity context. For `T0`, the Identity engine mints a **Minimal Anonymous Token**:
- `sub`: `anon:{session_id}`
- `act`: `svc:enterprise-agent-runtime`
- `aud`: `public-read-tools` (e.g., `kb_search`, `system_status`)
- This ensures that down-level audit logs, tenant boundary filters, and rate-limiting daemons evaluate all requests through a uniform cryptographic interface.

---

### Pillar C: Token Lifespan Synchronization & The 24-Hour Rule (`UA-D9`)

A pervasive failure mode in enterprise web applications is the mid-session token expiration fault ($KK3$):
- Standard OAuth2 access tokens expire after 60 minutes ($t_{\text{token}} = 1\text{h}$).
- Enterprise support sessions remain active up to the 12-hour absolute ceiling ($t_{\text{session}} = 12\text{h}$, `UA-D6`).
- Under naive implementations, an active user conversing in hour 2 triggers unexpected downstream 401 Unauthorized errors mid-turn.

#### Mathematical Alignment & The Fixed Rule
To eliminate the expiry variant of $KK3$, we formally specify:

$$T_{\text{validity}}(\text{User Access Token}) = 24\text{ hours}$$

$$\forall t \in [0, T_{\text{session\_cap}}], \quad t \le 12\text{ hours} < 24\text{ hours} \implies P(\text{Mid-Session Expiry}) \equiv 0$$

- The user access token outlives the 12-hour session cap, guaranteeing uninterrupted execution.
- Downstream exchanged OBO tokens remain short-lived ($15\text{ minutes}$) and are minted just-in-time per tool invocation activity.
- The 24-hour theft window is owned and mitigated via server-side session revocation checks and TLS channel binding.

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Tiered Identity Assurance (`UA-D3`)**:
   - Support three formal tiers: `T0_ANON`, `T1_VERIFIED`, and `T2_SSO`.
   - Tool permissions and intent execution are bounded strictly by tier. The agent runtime issues an interactive challenge when an action requires elevation.
2. **RFC 8693 Downstream Delegation (`UA-D4`)**:
   - All tool calls execute using RFC 8693 on-behalf-of tokens carrying `sub` (user) and `act` (agent) claims.
   - Anonymous users receive a minimal `T0` token restricted to a read-only audience (`UA-Q1(ii)`).
3. **24-Hour Token Validity (`UA-D9`)**:
   - User ingress tokens carry a 24-hour lifetime, completely preventing mid-session expiry across the 12-hour session lifecycle.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TIERED IDENTITY & TOKEN EXCHANGE ARCHITECTURE                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                     [Inbound Turn Received]
                                                   │
                                                   v
                                   ┌───────────────────────────────┐
                                   │  JWT Validator & Token Parser │
                                   └───────────────┬───────────────┘
                                                   │
                     ┌─────────────────────────────┼─────────────────────────────┐
                     │ [No Token]                  │ [OTP Code Validated]        │ [OIDC SSO Token]
                     v                             v                             v
           ┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
           │   Tier 0: ANON   │          │ Tier 1: VERIFIED │          │   Tier 2: SSO    │
           │ sub = anon_uuid  │          │ sub = phone/email│          │ sub = user_guid  │
           └─────────┬────────┘          └─────────┬────────┘          └─────────┬────────┘
                     │                             │                             │
                     v                             v                             v
           ┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
           │  Audit Context   │          │  Audit Context   │          │  Audit Context   │
           │  Audience: Read  │          │  Audience: Status│          │  Audience: Full  │
           └─────────┬────────┘          └─────────┬────────┘          └─────────┬────────┘
                     │                             │                             │
                     └─────────────────────────────┼─────────────────────────────┘
                                                   │
                                                   v
                                   ┌───────────────────────────────┐
                                   │ Security Token Service (STS)  │
                                   │ RFC 8693 On-Behalf-Of Minter  │
                                   │ (sub=user, act=agent, 15m TTL)│
                                   └───────────────┬───────────────┘
                                                   │
                                                   v
                                   [Dispatched to Tool Activities]
```

---

### Concrete Genesis Implementation Contracts

#### 1. Identity Context Models (`core/identity/models.py`)

```python
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class AssuranceTier(str, Enum):
    T0_ANON = "T0_ANON"
    T1_VERIFIED = "T1_VERIFIED"
    T2_SSO = "T2_SSO"

class IdentityContext(BaseModel):
    principal_id: str = Field(description="User UUID or anon:{session_id}")
    tenant_id: str
    email: Optional[str] = None
    assurance_tier: AssuranceTier
    roles: List[str] = Field(default_factory=list)
    token_issued_at: datetime
    token_expires_at: datetime
    session_id: str

class DownstreamDelegationToken(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int = 900  # 15 minutes
    audience: str
    subject: str
    actor: str = "svc:enterprise-agent-runtime"
```

#### 2. RFC 8693 Token Exchange Client (`core/identity/token_exchange.py`)

```python
import httpx
from datetime import datetime, timedelta
from core.identity.models import IdentityContext, AssuranceTier, DownstreamDelegationToken

class TokenExchangeService:
    def __init__(self, sts_endpoint: str, client_id: str, client_secret: str):
        self.sts_endpoint = sts_endpoint
        self.client_id = client_id
        self.client_secret = client_secret

    async def mint_on_behalf_of_token(
        self,
        identity: IdentityContext,
        target_audience: str
    ) -> DownstreamDelegationToken:
        """
        Executes RFC 8693 Token Exchange.
        UA-D4: Mints a short-lived token carrying sub (user) and act (agent).
        """
        # Enforce T0 Read-Only Audience Restriction (UA-Q1 -> ii)
        if identity.assurance_tier == AssuranceTier.T0_ANON:
            if target_audience not in ("https://api.enterprise.com/public-kb", "https://api.enterprise.com/status"):
                raise PermissionError("T0 Anonymous identity is restricted to read-only public audiences.")

        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "subject_token": identity.principal_id,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "actor_token": "svc:enterprise-agent-runtime",
            "actor_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "audience": target_audience,
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.sts_endpoint, data=payload, timeout=5.0)
            if response.status_code != 200:
                raise PermissionError(f"STS Token Exchange failed: {response.text}")
            
            data = response.json()
            return DownstreamDelegationToken(
                access_token=data["access_token"],
                expires_in_seconds=data.get("expires_in", 900),
                audience=target_audience,
                subject=identity.principal_id,
            )
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Mid-Session Token Expiration ($KK3$)** | User access token expires during a 4-hour active troubleshooting session. | **24-Hour Token Validity (`UA-D9`)**: User access token valid for 24h, comfortably exceeding 12h session cap. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **T1 Code Brute-Force ($KK5$)** | Attacker brute-forces 6-digit OTP code to elevate anonymous session to T1. | **Attempt Limits & TTL**: OTP has max 3 attempts and 5-minute expiry; protected by rate limiter (`RP-ADP-01`). |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Step-Up Funnel Abandonment ($KU2$)** | Requiring step-up to T2 causes user to abandon session (Erlang A abandonment). | **Lazy Elevation**: Agent defers step-up challenge to the exact turn preceding data disclosure or mutation. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Claimed vs Verified Confusion ($UK3$)** | User states *"My account is ACME-42"*; agent treats claimed ID as verified ID. | **Token Authority Invariant**: Context assembler populates account numbers strictly from verified JWT claims, never prompt text. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Anonymous Data Scraping ($UU2$)** | Scrapers use `T0` tokens to enumerate customer orders via read tools. | **T0 Audience Restrictiveness (`UA-Q1`)**: `T0` tokens cannot query endpoints accepting customer-specific identifiers. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Shared Kiosk Session Bleed ($UK5$)** | A user leaves a public kiosk open; next user inherits active T2 session. | **12-Hour Absolute Cap (`UA-D6`)**: Sessions terminate at 12 hours; high-risk actions prompt for re-authentication. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Mid-Turn Privilege Hijack ($UU3$)** | Session steps up T0 $\to$ T2; earlier prompt injection in T0 turn now executes with T2 authority. | **Assurance-Level Turn Tagging**: Every turn in history is tagged with the assurance tier at creation; sensitive tools ignore T0 prompts. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Orphaned OBO Token Leak ($KK6$)** | User logs out, but in-flight background activity holds valid 15-minute OBO token. | **Immediate Activity Abort**: Logout signal to Temporal cancels all in-flight activities and invalidates session token in Redis. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Step-Up Conversion Tracking**:
   - The system emits `StepUpChallengedEvent` and `StepUpCompletedEvent`.
   - Conversion rates are monitored across tenant cohorts. If drop-off exceeds 25%, the UX team is alerted to optimize authentication modals (`EV-ADP-05`).
2. **Delegation Audit Logs**:
   - Every RFC 8693 token exchange is logged with dual identity metadata (`principal_id`, `actor_service`, `audience`, `tier`) for SOC2 and ISO 27001 compliance auditing (`DP-ADP-03`).

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/identity/models.py`: Pydantic schemas for `IdentityContext`, `AssuranceTier`, and `DownstreamDelegationToken`.
2. `core/identity/authenticator.py`: Middleware validating ingress JWTs, extracting claims, and verifying 24h validity.
3. `core/identity/token_exchange.py`: The `TokenExchangeService` client communicating with enterprise STS.
4. `core/identity/step_up.py`: Logic managing interactive authentication challenges.

### Scaffolding Verification Criteria
- [ ] **T0 Audience Boundary Test**: Attempting to exchange a `T0_ANON` token for a billing audience raises an immediate `PermissionError`.
- [ ] **Dual-Identity Assertion**: Decoded OBO tokens carry both verified `sub` (user) and `act` (agent) claims.
- [ ] **Token Lifespan Check**: Unit tests verify that user access tokens reject lifetimes under 24 hours.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Complete Elimination of Confused Deputy Risk**: Downstream systems receive cryptographically verified on-behalf-of tokens specifying user identity and agent actor roles.
- **Minimal User Friction**: FAQ and product exploration require zero authentication, maximizing customer deflection and satisfaction.
- **Zero Mid-Session Authentication Drops**: 24-hour token validity prevents random mid-conversation authorization failures.
- **Granular Security Auditing**: Enterprise security operations can trace every downstream modification to both the requesting end-user and the AI agent instance.

### Negative / Neutral Trade-offs & Mitigations
- **STS Token Exchange Latency**: Exchanging tokens before tool execution adds 25–60ms.  
  *Mitigation*: Cache exchanged OBO tokens locally in Redis for 12 minutes (safely within the 15-minute TTL).
- **Expanded Token Theft Window (24h)**: A compromised client token remains valid for 24 hours.  
  *Mitigation*: Enforce TLS 1.3 channel binding and immediate server-side revocation on explicit logout.

---

## 8. References

1. **Hardy, N. (1988)**. *The Confused Deputy: (or why I am not a sympathizer with the access control list/capabilities controversy)*. ACM SIGOPS Operating Systems Review, 22(4), 36-38.
2. **IETF (2020)**. *OAuth 2.0 Token Exchange (RFC 8693)*. Internet Engineering Task Force.
3. **NIST (2020)**. *Digital Identity Guidelines: Authentication and Lifecycle Management*. NIST Special Publication 800-63B.
4. **Saltzer, J. H., & Schroeder, M. D. (1975)**. *The protection of information in computer systems*. Proceedings of the IEEE, 63(9), 1278-1308.
5. **Dixon, M., Toman, N., & DeLisi, R. (2010)**. *Stop Trying to Delight Your Customers*. Harvard Business Review.
