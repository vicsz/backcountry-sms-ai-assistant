TARGET ?= x86_64-unknown-linux-gnu
PROFILE ?= release
BUILD_CMD ?= cargo build
BUILD_COMMIT ?= $(shell git rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
BUILD_TIME_UTC ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
ARTIFACT := target/$(TARGET)/$(PROFILE)/bootstrap
PACKAGE_DIR := dist
ARCHIVE_DIR := target/package
PACKAGE := $(ARCHIVE_DIR)/backcountry-rust-runtime.zip

.PHONY: fmt check test clippy build package clean

fmt:
	cargo fmt --all -- --check

check:
	cargo check --locked

test:
	cargo test --locked

clippy:
	cargo clippy --locked --all-targets --all-features -- -D warnings

build:
	BUILD_COMMIT="$(BUILD_COMMIT)" BUILD_TIME_UTC="$(BUILD_TIME_UTC)" $(BUILD_CMD) --locked --release --target $(TARGET)

package: build
	install -d $(PACKAGE_DIR)
	install -m 0755 $(ARTIFACT) $(PACKAGE_DIR)/bootstrap
	install -d $(ARCHIVE_DIR)
	install -m 0755 $(ARTIFACT) $(ARCHIVE_DIR)/bootstrap
	cd $(ARCHIVE_DIR) && zip -q -X backcountry-rust-runtime.zip bootstrap

clean:
	cargo clean
	rm -rf $(PACKAGE_DIR) $(ARCHIVE_DIR)
