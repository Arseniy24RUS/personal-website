# How to configure Scopus in GitHub Actions

1. Open the repository on GitHub.
2. Go to `Settings` → `Secrets and variables` → `Actions`.
3. Create a repository secret for the Scopus API key.
4. Optional: create a repository secret for an Elsevier institutional token, if Elsevier provides one.
5. Run `Actions` → `Refresh scientist portfolio data` → `Run workflow`.

Do not put keys into:

- `public/`
- frontend React/JS code
- static JSON files
- committed YAML/MDX content

For GitHub Pages, the correct architecture is: secret in GitHub Actions → data snapshot JSON → static website.
