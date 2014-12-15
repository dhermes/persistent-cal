help:
	@echo 'Makefile for persistent-cal                            '
	@echo '                                                       '
	@echo 'Usage:                                                 '
	@echo '   make deploy         Deploy application to App Engine'

deploy:
	python setup_dependencies.py
	appcfg.py update .

.PHONY: deploy help
