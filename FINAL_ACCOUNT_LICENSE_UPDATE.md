# Final Account + License Update

Implemented after the Phase 9–13 handoff.

## Customer-facing behavior

### First run
- Fresh installation has no user and no license.
- The login page exposes a first-run setup route only while zero users exist.
- The operator enters username + password once.
- The account and `Operator` profile are created atomically.
- The initial 365-day license is created atomically at that same moment.
- No activation code is requested for the initial license.

### After first account creation
- The setup route redirects to the normal login page.
- There is no normal registration/sign-up flow.
- The application is single-user at the customer level.
- Login accepts only the existing username/password.
- Repeated activation calls cannot reset an existing license.

### Expired license
- Normal application requests are blocked by the existing license middleware.
- The authenticated operator can reach the renewal page.
- Correct renewal credential starts another 365-day period.
- Renewal cannot create a missing initial license.
- Accounting data is not modified by renewal.

## Validation

- Added integration-level tests for first-run setup, single-user enforcement, login availability before activation, activation-once behavior, and renewal-without-license protection.
- Python source compilation (`compileall`) completed successfully in the build environment.
- The complete Django test suite was not executed in this build environment because the required third-party packages are not installed here and outbound package download is unavailable. Run the full suite on the Windows Python 3.11.9 environment after installing `requirements.txt`.
