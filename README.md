# mags-mlops-prod-demo

A production-style MLOps demo for model serving and model management.

## Scope

- **Model management**: training, versioning, and a model registry.
- **Model serving**: packaging models behind a prediction API.
- **CI/CD**: automated testing and deployment with GitHub Actions (`.github/workflows/`).

## Getting started

Setup steps will be added as the project takes shape.

## Configuration

Keep secrets and local settings in a `.env` file. Never commit it; `.gitignore` already excludes all `.env` files except `.env.example`.

## Project structure

```
.github/workflows/   CI/CD pipelines (GitHub Actions)
```
