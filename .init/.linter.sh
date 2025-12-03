#!/bin/bash
cd /home/kavia/workspace/code-generation/multi-tenant-rbac-backend-system-40616-40582/rbac_backend_api
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

