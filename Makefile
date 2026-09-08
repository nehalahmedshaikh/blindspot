.PHONY: fetch build model validate export test serve all

fetch:
	PYTHONPATH=src python3 -m blindspot fetch

build:
	PYTHONPATH=src python3 -m blindspot build

model:
	PYTHONPATH=src python3 -m blindspot model

validate:
	PYTHONPATH=src python3 -m blindspot validate

export:
	PYTHONPATH=src python3 -m blindspot export

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

serve:
	python3 -m http.server 8000 --directory site

all: fetch build model validate export test
