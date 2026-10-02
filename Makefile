SENDER_EMAIL:=$(shell cat secrets/mailconfig.json | jq -r '.sender_email')
APP_PASSWORD:=$(shell cat secrets/mailconfig.json | jq -r '.app_password')
TO_EMAIL:=$(shell cat secrets/mailconfig.json | jq -r '.to_email')
DATA_PATH:=./data
CONFIG_PATH:=./config
UPDATE_FREQUENCY_SECONDS:=600
# DEBUG_MODE:=true

# Local SSL fix: homebrew Python 3.14 + corporate proxy can't use certifi's bundle.
# Point requests/urllib3 at the system OpenSSL store instead.
# Only applies if the file exists (macOS homebrew); harmless on Linux/Docker.
ifneq (,$(wildcard /opt/homebrew/etc/openssl@3/cert.pem))
REQUESTS_CA_BUNDLE:=/opt/homebrew/etc/openssl@3/cert.pem
endif

.EXPORT_ALL_VARIABLES:

venv:
	python3 -m venv venv

run:
	source venv/bin/activate && python3 feeder.py

feeder:
	source venv/bin/activate && python feeder.py


requirements:
	source venv/bin/activate && pip install -r requirements.txt

freeze:
	source venv/bin/activate && pip freeze

build:
	docker build -t feeder .
