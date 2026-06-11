PORT ?= auto
MPREMOTE := uvx --from mpremote mpremote

.PHONY: build test sync deploy reset repl tree info clean

build:
	bun esp/tools/build.mjs

test:
	python3 -m unittest discover -s esp/tests -v

sync: build
	$(MPREMOTE) connect $(PORT) fs cp -r esp/build/* :

deploy: sync
	$(MPREMOTE) connect $(PORT) reset

reset:
	$(MPREMOTE) connect $(PORT) reset

repl:
	$(MPREMOTE) connect $(PORT) repl

tree:
	$(MPREMOTE) connect $(PORT) fs ls :
	$(MPREMOTE) connect $(PORT) fs ls :app
	$(MPREMOTE) connect $(PORT) fs ls :lib

info:
	$(MPREMOTE) connect $(PORT) exec "import sys,gc; print(sys.implementation); print('heap',gc.mem_free())"

clean:
	rm -rf esp/build esp/.build-tmp
