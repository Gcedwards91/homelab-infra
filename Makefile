.PHONY: build-weather build-statporter build-demo push-weather push-statporter push-demo build-all push-all all

build-weather:
	docker build -t burningstar4/weather-app:latest weather-app/docker-src/

build-statporter:
	docker build -t burningstar4/statporter:latest weather-app/docker-final/statporter/

build-demo:
	docker build -t burningstar4/demo-container:latest weather-app/demo-container/

push-weather:
	docker push burningstar4/weather-app:latest

push-statporter:
	docker push burningstar4/statporter:latest

push-demo:
	docker push burningstar4/demo-container:latest

build-all: build-weather build-statporter build-demo

push-all: push-weather push-statporter push-demo

all: build-all push-all
