---
doc_id: kb-runbook-pos-gateway-store-guide
title: Nimbus POS Gateway store troubleshooting guide: red screen and error codes
source_system: runbooks
source_kind: operational
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-25
intents: [TECHNICAL_OUTAGE, GENERAL_INQUIRY]
test_case: none
---

# Nimbus POS Gateway store troubleshooting guide: red screen and error codes

## Why your cash register screen is red and cannot charge customers

When a retail cash register connected to **Nimbus POS Gateway** turns completely red and blocks card payments, the register's safety lock has engaged to prevent unrecorded or duplicate card charges during a communication failure. Follow this quick store guide to identify the error code on your register screen, check the Nimbus Status Page, and restore checkout service.

## Step 1: Check the Nimbus Status Page and read the error code

1. **Check Live Platform Status:** On any smartphone or back-office computer, open **`https://status.nimbuscloud.example.com`** and check the **Nimbus POS Gateway (US or EU Retail Relay)** indicator.
2. **Locate the Error Code on Your Register:** Look at the **top-right corner of the red register screen**. You will see one of three error codes:
   - **`POS-OFFLINE (0x104)`**
   - **`GATEWAY_TIMEOUT (0x504)`**
   - **`CARD-DECLINED-GATEWAY (0x402)`**

## Step 2: Follow the recovery steps for your specific error code

### How to fix `POS-OFFLINE (0x104)` (Store internet or local network issue)

`POS-OFFLINE` means the cash register cannot reach the internet or the Nimbus Cloud Platform gateway (`pos-us.nimbuscloud.example.com:8443` or `pos-eu.nimbuscloud.example.com:8443`). Nimbus Cloud Platform itself is usually operational when `POS-OFFLINE` appears on a single store's registers.

1. **Open the POS Diagnostic Overlay:** Tap the top-left Nimbus logo **5 times** on the touchscreen (or press **`Ctrl + Shift + D`** on a physical keyboard) and tap **Run Network Check**.
2. **Verify Store Wi-Fi / Ethernet:** Check that the register's Ethernet cable is seated or that the register is connected to the dedicated **Store-POS** Wi-Fi network (not the public guest Wi-Fi).
3. **Check Firewall Port `8443`:** If your store router was recently updated, ask your store IT team to confirm that outbound TCP port **`8443`** and UDP port **`123`** (NTP clock sync) are open.
4. **Restart the Local POS Agent:** Tap **Restart POS Service** in the diagnostic menu (or run the command below from the back-office store controller):

```bash
# Restart the local Nimbus POS Gateway agent and verify connectivity
nimbus-pos-cli service restart --verify-handshake
```

### How to handle `GATEWAY_TIMEOUT (0x504)` (Upstream payment relay timeout)

`GATEWAY_TIMEOUT` means your store internet is working and your register reached Nimbus POS Gateway, but the payment processor took longer than **8 seconds** to respond.

1. **Customer Cards Are Protected Against Double Charges:** Whenever `GATEWAY_TIMEOUT` occurs, Nimbus POS Gateway automatically sends an **instant reversal (`ISO-8583 0420`)** using the transaction's `Idempotency-Key`. Any temporary pending hold on a customer's card is automatically voided.
2. **Refresh the Relay Session:** Open the POS Diagnostic Overlay (**5 taps on the top-left logo** or **`Ctrl + Shift + D`**) and tap **Switch to Backup Relay Pool**.
3. **Escalate Immediately if Multiple Registers Are Red:** If switching to the backup relay pool does not clear the red screen within 60 seconds, ask for a **human support specialist** in the Nimbus Support web chat so our on-call engineering team (`queue-tech-sre`) can fail over your tenant's regional relay tunnel.

### How to fix `CARD-DECLINED-GATEWAY (0x402)` (Terminal certificate or issuer decline)

- If `CARD-DECLINED-GATEWAY` occurs for **only one shopper's card**, the shopper's bank declined the card (`05 Do Not Honor` or insufficient funds); ask the shopper for another payment method.
- If `CARD-DECLINED-GATEWAY` occurs for **every card on one specific register**, that terminal's pairing certificate has expired. Have a **POS Store Manager** or **Infrastructure Operator** sign in to the Nimbus console and click **POS Gateway > Terminals > Re-Pair Terminal**.
