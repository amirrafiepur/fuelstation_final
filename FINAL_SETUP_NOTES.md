# 140 Jahan Pour — Final Account & License Flow

## Single-user rule

The installed application is a single-operator application.

- On a fresh installation, there are no Django users and no license.
- The first-run setup page creates exactly one Django User and its Operator profile.
- The first successful account creation atomically starts the 365-day license.
- Once any User exists, the first-run setup route is no longer available.
- There is no normal user-registration/sign-up flow after setup.
- Normal use has only the login form (username + password) and logout.
- Creating additional users through the first-run UI is impossible.

The Django admin remains available in the source project for developer/maintenance work, but it is not linked from the customer-facing UI and the normal operator account is not a staff account.

## Initial license activation

The initial license is created only as part of the first successful account creation.
The activation date is the system's current local date at that moment. The accounting month still begins on day 1 of that calendar month, independently of the license date.

Calling the activation service again cannot reset an existing license.

## Renewal

After expiry, the authenticated operator is redirected to the renewal page. A correct renewal credential starts another 365-day period from the renewal date. Renewal never creates a missing initial license and never changes accounting records.

The renewal credential is represented only by a Django password hash in source code; plaintext is not stored in the application.

## Fresh installation flow

1. Start the packaged application.
2. Open the first-run setup page from the login screen.
3. Enter the only operator's username and password.
4. Submit once.
5. The account and Operator profile are created and the 365-day license begins automatically.
6. The application opens the dashboard.
7. Future launches show only the normal login screen.
