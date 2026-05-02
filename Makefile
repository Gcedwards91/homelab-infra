.PHONY: build-weather build-statporter push-weather push-statporter all

build-weather:
	docker build -t burningstar4/weather-app:latest weather-app/docker-src/

build-statporter:
	docker build -t burningstar4/statporter:latest weather-app/docker-final/statporter/

push-weather:
	docker push burningstar4/weather-app:latest

push-statporter:
	docker push burningstar4/statporter:latest

all: build-weather build-statporter push-weather push-statporter
