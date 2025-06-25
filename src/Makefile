all: fxs
.PHONY: all

include $(NCS_DIR)/src/ncs/build/include.ncs.mk

SRC = $(wildcard yang/manodc.yang)
DIRS = ../load-dir
FXS = $(SRC:yang/%.yang=../load-dir/%.fxs)

YANGPATH += ./yang ../../resource-manager/src/yang ../../inventory-manager/src/yang

NCSCPATH   = $(YANGPATH:%=--yangpath %)
YANGERPATH = $(YANGPATH:%=--path %)

fxs: $(DIRS) $(FXS)

$(DIRS):
	mkdir -p $@

../load-dir/%.fxs: yang/%.yang
	$(NCSC)  `ls $*-ann.yang  > /dev/null 2>&1 && echo "-a $*-ann.yang"` \
		--fail-on-warnings \
		$(NCSCPATH) \
		-c -o $@ $<

clean:
	rm -rf $(DIRS)
.PHONY: clean

draw:
	$(info ============= YANG tree to README =============)
	@sed -i '/^## Model Tree/,$$d' ../README.md
	@if [ -n "$$(tail -n 1 ../README.md)" ]; then echo "\n">> ../README.md; fi
	@echo "## Model Tree\n\`\`\`" >> ../README.md
	@pyang -f tree `grep -m 1 -R "module..*{" . --include *.yang | cut -d ":" -f 1` --ignore-errors > ../README.md
	@echo '```' >> ../README.md
	@$(MAKE) remove_fluff

# Check if 'ncs:plan-data' is used in YANG, find fluff area
# and cut it out. Works for multiple servicepoint models.
remove_fluff:
	@PLAN=$$(grep -R "uses ncs:plan-data;" . --include *.yang); \
	if [ -n "$${PLAN}" ] && ! echo "$${PLAN}" | grep -q "//"; then \
		RANGE="401"; \
	else \
	RANGE="366"; \
	fi; \
	while : ; do \
	START=$$(grep -n "+---x check-sync" ../README.md -m 1 | cut -d ":" -f 1); \
	END=$$(($${START} + $${RANGE})); \
	if [ -z "$${START}" ]; then \
		break; \
	fi; \
	sed -i "$${START},$${END}d" ../README.md; \
	done