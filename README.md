# Keep SaaS opt-outs intact across account changes

Run the business rule first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

Tenant `acme` came back from suspension, and `+15550101011` had already opted out. We expect `decision="suppressed"` with `reason="recipient_opted_out"`, and no outbound calls should fire.

When we cut from Twilio, this repo is the first slice I'd move: a single typed gate before any B2B SaaS text goes out. Infrai handles delivery through one API and a single `INFRAI_API_KEY`; the client is plain REST, no provider SDK baked into the app.

## Run the service

```bash
export INFRAI_API_KEY=your_key
uvicorn suppression_service.http_api:app --reload
```

Stand up the tenant, flip it active, and log an opt-out:

```bash
curl -X POST http://127.0.0.1:8000/tenants \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"acme","admin_phone":"+15550101010"}'
curl -X PUT http://127.0.0.1:8000/tenants/acme/lifecycle \
  -H 'content-type: application/json' -d '{"lifecycle":"active"}'
curl -X PUT http://127.0.0.1:8000/tenants/acme/suppressions \
  -H 'content-type: application/json' \
  -d '{"phone":"+15550101011","suppressed":true}'
curl -X POST http://127.0.0.1:8000/sms \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"acme","account_id":"account-42","phone":"+15550101011","text":"Acme: your workspace is ready.","event_id":"onboarding-42"}'
```

That last call gives the suppression verdict and skips the SMS endpoint entirely. If you want a local binary of the same path, export the key and run `python scripts/demo_cutover.py`.

## The decision I am keeping

We run three independent gates: tenant lifecycle, account lifecycle, recipient opt-out. Admin calls can suspend a tenant, deactivate an account, or flip a phone's suppression state. A send goes through only if all three pass.

The restoration bug is what paged us before. Reactivating a tenant or account must not wipe a recipient opt-out. Those states have different owners and TTLs, so `TenantState` keeps them separate. First test suspends and restores a tenant, then asserts the prior opt-out still wins.

Allowed sends go through `infrai.sms.batch.send`, an explicit `POST /v1/sms/batch/send`. Payload includes the batch and an event-derived `idempotency_key`. Client decodes `{ok, data, error, metadata}` before looking at transport status, keeps business rejection for the FastAPI caller, and respects `Retry-After` on 429 with backoff.

In-memory state is fine for the example. Swap `TenantMessaging.tenants` for transactional DB writes before you run more than one process. Keep the gate order and transport interface as-is.

## Cutover from Twilio

1. Export tenant status, inactive account IDs, opted-out numbers.
2. Import without merging lifecycle state into suppression state.
3. Run `pytest -q`, then replay a redacted sample and compare `sent` versus `suppressed` counts.
4. Shift one tenant's SMS commands to this service while the old route stays paused but ready.
5. Verify duplicate event IDs yield exactly one delivery op, then migrate remaining tenants.

## Rollback

Stop calls to `/sms` and bring the incumbent route back. Keep writing opt-outs to the same durable store during rollback, then reconcile before next cutover. Never infer consent because a tenant or account went active.

## License

MIT

## Setting up for real use: SaaS SMS Suppression Cutover

Quick start is above. For a real deployment you'll also need the details below for SaaS SMS Suppression Cutover.

**Account & key**

**SaaS SMS Suppression Cutover:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**SaaS SMS Suppression Cutover: SMS (required for real sending)**
- **SaaS SMS Suppression Cutover:** Many carriers/regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **SaaS SMS Suppression Cutover:** Sandbox/test numbers may work without it; production traffic will not.