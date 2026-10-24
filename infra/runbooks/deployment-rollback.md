# Deployment Rollback

1. Stop promotion if CI or smoke tests fail.
2. Identify last known-good release and compatible schema.
3. Roll back application code/image when safe.
4. Do not blindly reverse destructive migrations; use a reviewed forward fix or restore.
5. Run health checks and critical workflow smoke tests.
6. Document impact and fix the release pipeline.
