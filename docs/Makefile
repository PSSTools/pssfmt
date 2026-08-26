# Minimal makefile for Sphinx documentation.
#
# SPHINXBUILD points into the ivpm venv by default, matching
# pssparser/docs/Makefile: `make html` then works from a fresh checkout with
# no activation step, which is the difference between a docs build people run
# and one they do not.
DOCS_DIR:=$(dir $(abspath $(lastword $(MAKEFILE_LIST))))

SPHINXOPTS    ?=
SPHINXBUILD   ?= $(DOCS_DIR)/../packages/python/bin/sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# What CI runs (T-10, D-16). Warnings are errors: a broken cross-reference is
# a documentation bug, and the only way it stays fixed is if it fails a build.
strict:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" -W --keep-going $(SPHINXOPTS) $(O)

.PHONY: help strict Makefile

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
