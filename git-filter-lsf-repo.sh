#!/usr/bin/env bash

echo "========================================"
echo " Remove blobs larger than 100 MB"
echo "========================================"
echo

# Verify we're in a Git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: This is not a Git repository."
    echo
    read -p "Press Enter to exit..."
    exit 1
fi

# Verify git-filter-repo is installed
if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "ERROR: git-filter-repo is not installed."
    echo
    read -p "Press Enter to exit..."
    exit 1
fi

echo "This will permanently rewrite the repository history."
echo "All blobs larger than 100 MB will be removed."
echo

read -p "Continue? (y/N): " answer

if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    echo
    read -p "Press Enter to exit..."
    exit 0
fi

echo
echo "Rewriting history..."

git filter-repo \
    --force \
    --strip-blobs-bigger-than 100M

RESULT=$?

echo

if [ $RESULT -eq 0 ]; then
    echo "SUCCESS!"
    echo
    echo "You must now force-push:"
    echo "  git push --force --all"
    echo "  git push --force --tags"
else
    echo "FAILED (exit code $RESULT)"
fi

echo
read -p "Press Enter to exit..."