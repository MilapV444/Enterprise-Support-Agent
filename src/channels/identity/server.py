"""The full web API with real sign-in: the M1-01 turn and event routes plus /v1/identity/* routes.

    POST /v1/identity/anonymous   {tenant_id}                          -> T0 access token
    POST /v1/identity/otp/start   {tenant_id, user_id}                 -> challenge id (code goes to send_otp)
    POST /v1/identity/otp/verify  {tenant_id, challenge_id, code}      -> T1 access token
    POST /v1/identity/sso         {tenant_id, id_token, nonce}         -> T2 access token
    POST /v1/identity/logout      (Bearer)                             -> ends the session
    POST /v1/identity/mock-idp    {tenant_id, user_id, nonce, mfa}     -> ID token (only with a MockIdP)

Sign-in calls that carry the current Bearer token step up that session instead of starting a new one.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from channels.api.app import create_app
from channels.identity.otp import OtpError
from channels.identity.tiers import StepUpRequired
from channels.identity.tokens import TokenError


class TenantBody(BaseModel):
    tenant_id: str


class OtpStart(TenantBody):
    user_id: str


class OtpVerify(TenantBody):
    challenge_id: str
    code: str


class SsoBody(TenantBody):
    id_token: str
    nonce: str


class MockIdpBody(TenantBody):
    user_id: str
    nonce: str
    mfa: bool = True


def _bearer(request):
    header = request.headers.get("Authorization", "")
    return header.removeprefix("Bearer ") if header.startswith("Bearer ") else None


def _token(issue):
    try:
        return {"access_token": issue(), "token_type": "Bearer"}
    except (TokenError, OtpError) as error:
        raise HTTPException(401, str(error)) from None
    except StepUpRequired as error:
        raise HTTPException(403, {"step_up": error.required.name}) from None


def identity_router(identity, mock_idp=None):
    router = APIRouter(prefix="/v1/identity")

    @router.post("/anonymous")
    def anonymous(body: TenantBody):
        return _token(lambda: identity.anonymous(body.tenant_id))

    @router.post("/otp/start")
    def otp_start(body: OtpStart):
        return {"challenge_id": identity.start_otp(body.tenant_id, body.user_id)}

    @router.post("/otp/verify")
    def otp_verify(body: OtpVerify, request: Request):
        return _token(lambda: identity.verify_otp(body.tenant_id, body.challenge_id, body.code,
                                                  _bearer(request)))

    @router.post("/sso")
    def sso(body: SsoBody, request: Request):
        return _token(lambda: identity.sso(body.tenant_id, body.id_token, body.nonce, _bearer(request)))

    @router.post("/logout", status_code=204)
    def logout(request: Request):
        token = _bearer(request)
        if token is None:
            raise HTTPException(401, "a Bearer access token is required")
        try:
            identity.logout(token)
        except TokenError as error:
            raise HTTPException(401, str(error)) from None

    if mock_idp is not None:
        @router.post("/mock-idp")
        def mock_login(body: MockIdpBody):
            token = mock_idp.id_token(identity.client_id, body.tenant_id, body.user_id, body.nonce, body.mfa)
            return {"id_token": token}

    return router


def build_app(dsn, identity, mock_idp=None, **create_app_options):
    app = create_app(dsn, authenticate=identity.authenticate, **create_app_options)
    app.include_router(identity_router(identity, mock_idp))
    return app
