SENDER_EMAIL:=$(shell cat secrets/mailconfig.json | jq -r '.sender_email')
APP_PASSWORD:=$(shell cat secrets/mailconfig.json | jq -r '.app_password')
TO_EMAIL:=$(shell cat secrets/mailconfig.json | jq -r '.to_email')
# DEBUG_MODE:=true
.EXPORT_ALL_VARIABLES:

venv:
	python3 -m venv venv

run:
	source venv/bin/activate && python3 main.py
	#python3 webtoepub.py

run-dry:
	python3 webtoepub.py -n

requirements:
	source venv/bin/activate && pip install -r requirements.txt

freeze:
	source venv/bin/activate && pip freeze
