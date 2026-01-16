.DEFAULT_GOAL := help
.PHONY: requirements

# include *.mk

# Generates a help message. Borrowed from https://github.com/pydanny/cookiecutter-djangopackage.
help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@perl -nle'print $& if m{^[\.a-zA-Z_-]+:.*?## .*$$}' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m %-25s\033[0m %s\n", $$1, $$2}'

lang_targets = en es_419
create_translations_catalogs: ## Create the initial configuration of .mo files for translation
	pybabel extract -F gradeucursos/locale/babel.cfg -o gradeucursos/locale/django.pot --msgid-bugs-address=eol-ing@uchile.cl --copyright-holder=EOL --project=OPEN --version=0.1.0 --last-translator='EOL <eol-ing@uchile.cl>' *
	pybabel extract -F gradeucursos/locale/babel-js.cfg -o gradeucursos/locale/django-js.pot --msgid-bugs-address=eol-ing@uchile.cl --copyright-holder=EOL --project=OPEN --version=0.1.0 --last-translator='EOL <eol-ing@uchile.cl>' *
	for lang in $(lang_targets) ; do \
		pybabel init -i gradeucursos/locale/django.pot -D django -d gradeucursos/locale/ -l $$lang ; \
		pybabel init -i gradeucursos/locale/django-js.pot -D djangojs -d gradeucursos/locale/ -l $$lang ; \
	done

update_translations: ## update strings to be translated
	pybabel extract -F gradeucursos/locale/babel.cfg -o gradeucursos/locale/django.pot --msgid-bugs-address=eol-ing@uchile.cl --copyright-holder=EOL --project=OPEN --version=0.1.0 --last-translator='EOL <eol-ing@uchile.cl>' * 
	pybabel extract -F gradeucursos/locale/babel-js.cfg -o gradeucursos/locale/django-js.pot --msgid-bugs-address=eol-ing@uchile.cl --copyright-holder=EOL --project=OPEN --version=0.1.0 --last-translator='EOL <eol-ing@uchile.cl>' *
	pybabel update -N -D django -i gradeucursos/locale/django.pot -d gradeucursos/locale/
	pybabel update -N -D djangojs -i gradeucursos/locale/django-js.pot -d gradeucursos/locale/
	rm gradeucursos/locale/django.pot
	rm gradeucursos/locale/django-js.pot

compile_translations: ## compile .po files into .mo files
	pybabel compile -f -D django -d gradeucursos/locale/; \
	pybabel compile -f -D djangojs -d gradeucursos/locale/
