# Security policy

## Reporting a vulnerability

Do not publish credentials, save files, database files, or exploit details in an
issue. Contact the repository owner privately through the GitHub security
advisory flow once enabled.

## Current security boundaries

- Passwords are salted and hashed with scrypt.
- Owner sessions are HttpOnly, same-origin cookies with expiry.
- Viewer payloads exclude raw save bytes, password material, internal IDs, and
  save hashes.
- Upload size is bounded before parsing.
- The free Render deployment is ephemeral and is not suitable for sensitive or
  permanent data.

Known missing production controls include password recovery, login rate
limiting, account lockout/audit events, managed database backups, and a formal
secret-rotation process.

