# B5 Sandbox rehearsal (work in progress)

Do not treat B5 as passed until the fresh integrated flow and recovery are
verified on the deployed commit. Fulfillment and inventory are synthetic;
OpenRouter and PayPal Sandbox calls are real.

## Prepare deployment

The additive `003_b5_fulfillment.sql` migration must run after the domain and
earlier payment migrations. The existing `B2_RUN_MIGRATIONS=true` startup flag
applies both sets; coordinate this shared-database change with the team, check
the `B2 domain and payment migrations completed` log, then turn it off. Keep
the B2/B3 harness and fault flags off.

For the coordinated B5 test, the web service needs `B4_ENABLED=true`,
`B5_CAPTURE_ENABLED=true` and a separate server-side `B4_MERCHANT_TOKEN` with
at least 32 characters. Keep `B5_ALLOW_FAULT_INJECTION=false` except during
the single planned lost-response rehearsal. Keep the token out of Git, chat,
screenshots and browser JavaScript. Existing B4 database and session settings
must remain unchanged.

The user reported adding the synthetic `b5_friday_navy` and `b5_monday_black`
batches. Availability can change; recheck before starting. Do not re-seed or
reset allocations to force a test. Obtain a new buyer-approved authorization;
do not capture the earlier B4 authorization as part of this rehearsal.

## Merchant actions

On your own PowerShell, use the new authorization ID from the fresh buyer
checkout. The token prompt is visible to support pasting; do not share the
line containing the token or a terminal transcript that includes it.

```powershell
$service = "https://agentnegotiate.onrender.com"
$authId = Read-Host "Fresh B5 Sandbox authorization ID"
$merchantToken = Read-Host "B4 merchant token (keep private)"
$merchantHeaders = @{ Authorization = "Bearer $merchantToken" }
$base = "$service/api/merchant/payments/authorizations/$authId"
```

Confirm simulated fulfillment explicitly:

```powershell
Invoke-RestMethod -Method Post -Uri "$base/fulfillment" -Headers $merchantHeaders -ContentType "application/json" -Body '{"simulated":true}'
```

Expected: `status fulfilled`, `simulated True`. This is a demo assertion, not
evidence of actual shipment. A capture attempted before it must return 409.

During the one lost-response exercise, temporarily set
`B5_ALLOW_FAULT_INJECTION=true` on Render and wait for redeployment. Send:

```powershell
$faultHeaders = @{ Authorization = "Bearer $merchantToken"; "X-B5-Simulate-Lost-Response" = "true" }
try { Invoke-RestMethod -Method Post -Uri "$base/capture" -Headers $faultHeaders } catch { Write-Host "HTTP status:" $_.Exception.Response.StatusCode.value__ }
```

The expected 503 indicates the response was deliberately discarded; it does
not alone prove capture. Retry the **same authorization** without the fault
header while within one hour, then repeat once:

```powershell
Invoke-RestMethod -Method Post -Uri "$base/capture" -Headers $merchantHeaders
Invoke-RestMethod -Method Post -Uri "$base/capture" -Headers $merchantHeaders
```

Both successful responses must return `captured` and the same capture ID.
Check the Sandbox transaction's amount, currency, status and capture ID; check
the buyer's persisted payment status on refresh and again after service restart.
Never start another payment to work around an uncertain result. Outside the
automatic retry window or if the result remains uncertain, stop and reconcile
manually against PayPal and the stored operation; do not reset the database.

Disable `B5_ALLOW_FAULT_INJECTION` immediately after the exercise and disable
`B5_CAPTURE_ENABLED` outside the coordinated rehearsal. Clear local variables:

```powershell
Remove-Variable merchantToken,merchantHeaders,faultHeaders -ErrorAction SilentlyContinue
```

Record only the deployed commit, model ID, negotiation/quote/order/authorization/
capture IDs, amount, status and sanitized test results. Do not include tokens,
database URLs, cookies, raw model traces or provider response bodies.
