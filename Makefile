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
