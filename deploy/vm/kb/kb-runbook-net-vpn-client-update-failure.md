---
doc_id: kb-runbook-net-vpn-client-update-failure
title: Nimbus Net VPN client failure after update: certificate refresh and reinstall
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-26
intents: [TECHNICAL_OUTAGE, PASSWORD_RESET]
test_case: none
---

# Nimbus Net VPN client failure after update: certificate refresh and reinstall

## Symptoms and root cause of Nimbus Net VPN failures after update

Engineers and administrators connecting from macOS, Windows, or Linux workstations to a private **Nimbus Net** VPC using the **Nimbus Net WireGuard/OpenVPN Client (`nimbus-vpn-client`)** may encounter connection failures immediately after upgrading the client software (for example, upgrading from `v3.2.x` to `v3.4.0`) or after an operating-system update:

- **Error `VPN_ERR_TUN_DRIVER_MISMATCH (0x802)`:** The legacy virtual network kernel extension / `utun` interface from the previous version remained locked during the in-place upgrade.
- **Error `VPN_ERR_MTLS_CERT_EXPIRED_OR_INVALID (0x814)`:** Client `v3.4.0+` enforces TLS 1.3 and SHA-384 device client certificates, rejecting cached legacy SHA-1/RSA-1024 device certificates stored in `~/.config/nimbus-vpn/certs/`.

## Step-by-step remediation procedure

### Step 1: Stop the stuck daemon and purge stale virtual tunnel interfaces

1. Instruct the user to stop the background `nimbus-vpn-daemon` service and flush orphaned `utun` / `wg-nimbus0` network interfaces:

```bash
# Stop the Nimbus VPN daemon and remove orphaned tunnel interfaces (macOS / Linux)
sudo nimbus-vpn-cli daemon stop --force
sudo ip link delete wg-nimbus0 2>/dev/null || sudo ifconfig utun99 destroy 2>/dev/null
```

*(On Windows workstations, run `nimbus-vpn-cli.exe daemon stop --reset-wintun` from an elevated PowerShell prompt).*

### Step 2: Clean reinstall of the Nimbus Net VPN client package

1. Remove the corrupted in-place upgrade state while preserving user profile names, then install the clean `v3.4.0` package:

```bash
# Purge cached driver state and reinstall nimbus-vpn-client
nimbus-vpn-cli clean-driver-cache --preserve-profiles
# Verify client binary and WireGuard/Wintun driver version
nimbus-vpn-cli version --verify-driver
```

2. Confirm that `driver_status` reports `DRIVER_OK (v3.4.0_tls13_ready)`.

### Step 3: Refresh the short-lived device mTLS certificate via SSO

Because `nimbus-vpn-client v3.4.0+` requires an ECDSA P-384 device certificate bound to an MFA-verified identity session, flush the expired `~/.config/nimbus-vpn/certs/` bundle and pull a fresh certificate using the CLI SSO flow:

```bash
# Purge legacy device certificates and enroll a fresh ECDSA P-384 client certificate
nimbus-vpn-cli certs revoke-local --all
nimbus auth login --sso --tenant <TENANT_SLUG>
nimbus-vpn-cli certs refresh --vpc <VPC_NAME> --region <REGION>
```

### Step 4: Reconnect and verify private VPC DNS and routing

1. Bring up the VPN tunnel and verify that internal VPC DNS resolution (`*.internal.nimbus.local`) and private subnet routing (`10.42.0.0/16`) are operational:

```bash
# Connect to the Nimbus Net VPC VPN gateway and run the built-in connectivity check
nimbus-vpn-cli connect --profile <VPC_NAME> --verify-routes
nimbus-vpn-cli status
```

2. Confirm that `Tunnel State` shows `ESTABLISHED (mTLS 1.3 / WireGuard)` and `Handshake Age` is `< 10s`.
