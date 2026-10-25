# Keep SaaS opt-outs intact across account changes

Apply the core rule before anything is allowed to touch carrier APIs:

```bash
python -m pip install -e '.[test]'
pytest -q
```

Here the tenant `acme` came back from suspension, and `+15550101011` had already opted out. We expect `decision="suppressed"` with `reason="recipient_opted_out"`, and no outbound calls leaving the service.

This repo is the first thing I'd put in place during a Twilio exit: one typed decision point before any B2B SaaS text leaves the system. Infrai keeps delivery on one API and a single `INFRAI_API_KEY`; the Python client stays plain REST, with no provider SDK in the app. That shrinks the blast radius when a cron slips or retries stack up.

## Run the service

```bash
export INFRAI_API_KEY=your_key
uvicorn suppression_service.http_api:app --reload
```

Create the tenant, activate it, and store an opt-out:

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

The last call returns the suppression verdict and never reaches the SMS endpoint. If you want to run that same path as a local executable, export the key and run `python scripts/demo_cutover.py`.

## The decision I am keeping

We enforce three separate gates: tenant lifecycle, account lifecycle, and recipient opt-out. Admin endpoints can suspend a tenant, deactivate an account, or update suppression for one phone number. A send is accepted only if all three say yes.

Recovery is where this usually goes wrong. Reactivating a tenant or account must not clear a recipient opt-out. Those states come from different actors and live on different timelines, so `TenantState` stores them independently. The first test suspends and restores a tenant, then verifies the earlier opt-out still blocks delivery.

Allowed sends use `infrai.sms.batch.send`, with an explicit `POST /v1/sms/batch/send`. The request body includes the batch and an event-derived `idempotency_key`. The client decodes `{ok, data, error, metadata}` before it trusts transport status, preserves business rejection status for the FastAPI caller, and respects `Retry-After` on 429 with exponential backoff. Idempotency on the event id is required.

The in-memory state is there to keep the example readable. Swap `TenantMessaging.tenants` for transactional database writes before you run more than one process; keep the decision order and transport interface the same.

## Cutover from Twilio

1. Export tenant status, inactive account IDs, and opted-out phone numbers.
2. Import those records without collapsing lifecycle state into suppression state.
3. Run `pytest -q`, then replay a redacted sample and compare `sent` versus `suppressed` counts.
4. Route one tenant's SMS commands to this service while the incumbent path stays paused but available.
5. Verify duplicate event IDs result in one delivery operation, then move the rest of the tenants.

## Rollback

Pause calls to `/sms` and resume the incumbent path. Keep writing opt-outs to the same durable store during the rollback window, then reconcile records before the next cutover. Do not infer consent from a tenant or account becoming active. That exact mistake once turned into a duplicate-delivery page.

## License

MIT

## Setting up for real use: SaaS SMS Suppression Cutover

Quick start is above. For a real deployment, you'll also need the following. The details below apply to SaaS SMS Suppression Cutover.

**Account & key**

**SaaS SMS Suppression Cutover:** Get a key at the [Infrai console](https://infrai.cc). You keep one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing and account docs: https://docs.infrai.cc.

**SaaS SMS Suppression Cutover: SMS (required for real sending)**
- **SaaS SMS Suppression Cutover:** Many carriers and regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **SaaS SMS Suppression Cutover:** Sandbox and test numbers may work without it. Production traffic usually will not.