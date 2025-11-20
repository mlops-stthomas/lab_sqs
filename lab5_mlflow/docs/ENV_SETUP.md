# Environment & Credentials Setup (sanitized)

This project uses a uv workspace; keep real secrets out of git and load them at runtime.

## AWS (S3, Snowflake storage integration)
- Preferred: set `AWS_PROFILE` to a profile in `~/.aws/credentials` (boto3 picks it up automatically).
- Alternative: export `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION`.
- Snowflake external stage/storage integration: use `SF_STORAGE_INTEGRATION` and `S3_BUCKET` to point to your integration and bucket; credentials are not stored in code.

## Snowflake
- Populate the Snowflake variables (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_WAREHOUSE`, etc.) in a local `.env` (gitignored).
- For external stage access, rely on the configured storage integration (`SnowflakeServeAIStorageRole` or equivalent) rather than embedding keys.

## Neo4j
- Set Neo4j connection details (uri, username, password, database) per environment in `.env`; keep passwords out of git.
- For multiple instances, use distinct prefixes (e.g., `NEO4J_`, `PROPER_NEO4J_`, `TRAY_NEO4J_`).

## MLflow / API
- `MLFLOW_TRACKING_URI` and `MODEL_NAME` live in `.env`; no secrets are required if using local MLflow.

## Keeping secrets out of history
- Do not commit `.env` or credential files (already gitignored).
- If secrets were ever committed, rotate them immediately (AWS keys, Snowflake passwords, Neo4j passwords) and rewrite history with `git filter-repo`:
  ```
  pip install git-filter-repo  # if needed
  git filter-repo --path .env --invert-paths
  ```
  Then force-push the cleaned history to remove leaked blobs.
