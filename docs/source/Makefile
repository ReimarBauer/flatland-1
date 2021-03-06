# Makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
VERSION      ?= tip

# Internal variables.
ALLSPHINXOPTS = -d ../doctrees $(SPHINXOPTS) .
export PYTHONPATH=../..

all: html text

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  html      to make standalone HTML files"
	@echo "  text      to make standalone text files"
	@echo "  doctest   to run doctests"

clean:
	for i in doctrees html text doctest pickles website coverage; do \
	    rm -rf ../$$i; \
        done

html:
	mkdir -p ../html ../doctrees _static _template
	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) ../html
	@echo
	@echo "Build finished. The HTML pages are in ../html."

text:
	mkdir -p ../text ../doctrees
	$(SPHINXBUILD) -b text $(ALLSPHINXOPTS) ../text
	@echo
	@echo "Build finished. The text pages are in ../text."

website:
	mkdir -p ../website ../doctrees
	$(SPHINXBUILD) -b discorporate \
           -D html_theme=discorporate \
           -D version=$(VERSION) \
           $(ALLSPHINXOPTS) ../website

doctest:
	mkdir -p ../doctrees ../doctest
	$(SPHINXBUILD) -b doctest $(ALLSPHINXOPTS) ../doctest

coverage:
	mkdir -p ../coverage ../doctrees
	$(SPHINXBUILD) -b coverage $(ALLSPHINXOPTS) ../coverage

pickles:
	mkdir -p ../pickles ../doctest
	$(SPHINXBUILD) -b pickle $(ALLSPHINXOPTS) ../pickles
