# TraderX Authentication UI Contract

## Scope

This contract defines the browser-visible authentication journeys. It complements the HTTP API
contract; browser controls submit only to `/api/v1` and do not carry session tokens in browser
storage.

## Public and Protected Routes

| Route | Valid state | Required screen behavior | Invalid state behavior |
|---|---|---|---|
| `/` | Anonymous or authenticated | Public product boundary and links to valid entry route. | Never renders operational data. |
| `/setup` | No `IdentityBootstrapState` exists | Email, password, confirmation, one-time setup explanation. On success, go to `/mfa/enroll`. | When bootstrap is unavailable, redirect to `/sign-in` with an explanation. |
| `/sign-in` | Anonymous or expired | Email/password, password-reset link, and status/error region. Password success goes to `/mfa/enroll` or `/mfa/verify`. | An MFA-assured session redirects to `/command-center`. |
| `/mfa/enroll` | Current password-assured session with unconfirmed factor | Authenticator setup key, accessible copy instruction, code entry, recovery-code handoff. | Invalid, expired, or completed state redirects to `/sign-in`. |
| `/mfa/verify` | Current password-assured session with confirmed factor | TOTP code entry and recovery link. | Invalid, expired, or completed state redirects to `/sign-in`. |
| `/mfa-recovery` | Current password-assured session | One recovery-code entry; successful recovery requires fresh enrollment at `/mfa/enroll`. | Invalid or expired state redirects to `/sign-in`. |
| `/password-reset` | Anonymous | Reset request and reset-completion views; completion asks for reset token, new password, and TOTP or recovery code. | Used or expired challenge renders a neutral error and link to `/sign-in`. |
| `/command-center` and every operational route | Current MFA-assured session | Render only authorized user data and controls. | Expired or insufficient session redirects to `/sign-in?reason=session-expired` before a mutation is attempted. |

## Interaction Requirements

- Each form has a programmatic heading, labelled fields, a visible submit state, and an announced
  success/error message. Inputs for passwords, TOTP, and recovery codes use appropriate browser
  autofill semantics without persisting secrets in page state after completion.
- The initial-owner screen is available exactly once. It must explicitly state that later users are
  invited by an authorized user and must not imply public self-registration.
- The TOTP setup secret/URI is rendered only during active enrollment. Recovery codes are rendered
  once after confirmed enrollment with an explicit acknowledgement before navigation onward.
- A password-reset request returns a neutral confirmation regardless of account existence. Reset
  completion does not grant access until its second proof succeeds.
- A session-expiry redirect explains that no pending action was completed and preserves no secret
  form fields. Forms for high-risk actions must surface expiry before retrying.
- Recovery-code use, assisted reset, password reset, sign-in, sign-out, MFA success/failure, and
  session expiry produce the appropriate audit-visible security outcome without displaying
  security-sensitive internals to the user.

## Test Oracles

1. Concurrent visits to `/setup` create at most one owner.
2. Every direct auth-route visit shows only its permitted step and has no operational data in the
   response or accessibility tree.
3. A used code/token, expired challenge, or expired session cannot complete a mutation.
4. TOTP reuse fails; recovery-code reuse fails; each success revokes required sessions.
5. Password reset with only a reset token cannot reach `/command-center`.
6. Keyboard-only users can complete the owner setup, MFA enrollment, sign-in, recovery, reset, and
   session-expiry journeys.
