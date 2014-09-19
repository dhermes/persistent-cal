default:

.PHONY: deploy
deploy:
	python setup_dependencies.py
	appcfg.py update .
