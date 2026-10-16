# Vivek portfolio — GitHub-ready source

## GitHub upload
1. Extract this ZIP on your computer. Do not upload the ZIP itself as your website.
2. Create a PRIVATE GitHub repository. Choose Add file → Upload files.
3. Upload ALL extracted contents, including templates/ and static/, preserving folders. app.py and render.yaml must be at the repository root. Commit.
4. Never upload real keys, .env files, passwords, or private/ database files.

## Online deployment with Render
GitHub Pages cannot run this Python application. The included Render Blueprint uses a PAID Starter service and persistent disk. Review current pricing and approve it yourself before deployment.
1. Connect your repository to Render; create a Blueprint from render.yaml.
2. Set ADMIN_PASSWORD to a unique password of at least 14 characters.
3. Set DATA_KEY_B64 to base64 of 32 random bytes. Run python generate_keys.py locally to generate it (the script also prints a SESSION_SECRET, but Render automatically generates that secret in this Blueprint).
4. Deploy. The first startup automatically creates your owner account and encrypts initial content into SQLite. No initialization command is required.
5. Open the service URL. User opens the portfolio. Admin opens the password page.
6. Save profile/projects commits changes directly to SQLite. PDF and Word uploads save immediately.

## Local execution
Python 3.12 recommended. Create a virtual environment; install requirements.txt. Set SESSION_SECRET, DATA_KEY_B64, ADMIN_PASSWORD environment variables; for local plain HTTP set COOKIE_SECURE=0 and DATABASE_PATH=private/portfolio.db. Start with waitress-serve --listen=127.0.0.1:8080 app:app and open http://127.0.0.1:8080 . Environment files are not loaded automatically.

## Security and data notes
- AES-256-GCM encrypts the portfolio payload including original documents; SQL stores the ciphertext. Each save uses a new 96-bit nonce and authenticated context.
- Owner passwords use scrypt hashes, not reversible encryption. No default password/key is supplied.
- Server-side authorization, CSRF, HttpOnly/SameSite cookies, Secure cookies by default, CSP, parameterized SQL, input/file limits, throttling, idle/absolute session expiry are included.
- Public profile, projects and PDF remain intentionally public. HTML/JS delivered to browsers cannot be hidden or made totally secure.
- Word is owner-only. Upload validation checks basic signatures, not malware; upload trusted documents only.
- seed.json includes your ORIGINAL PLAINTEXT résumé and initial content for bootstrap. Keep the repository PRIVATE, or remove personal seed content before making it public. Git history may retain deleted data. Never serve the project folder directly as a static site. Render runs Flask; only static/ is public.
- On initial startup ADMIN_PASSWORD creates the owner. Later changing that environment variable does NOT reset the stored password. Keep a password manager copy. Password-reset workflow is not included in this build.
- Keep DATA_KEY_B64 unchanged and backed up separately from the database. Losing/changing it makes existing content unreadable. Never regenerate it on redeploy. SESSION_SECRET must also persist; rotating it logs everyone out.
- Persistent disk is REQUIRED for database durability. Back up the encrypted database and test restoration. Keys must be backed up separately. This is one-owner/single-process SQLite; edits are last-write-wins.
- Rate limiting is in-process, resets on restart, and uses direct peer IP. Put Internet deployment behind HTTPS and carefully configured proxy-level rate limiting. No forwarded IP headers are blindly trusted. A shared proxy IP may group users for the baseline limiter.
- No MFA, antivirus scanning, key rotation tool, audit trail or independent security audit is included. Use updated dependencies and security-test before handling sensitive data.

## Verification
Python source syntax, SQLite schema execution and ZIP structure were checked. Full browser, deployment and penetration testing were NOT performed. The interface reconstructs the requested appearance; the earlier generated HTML was not available for an exact patch.
