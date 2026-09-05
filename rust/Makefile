TARGET ?= x86_64-unknown-linux-gnu
PROFILE ?= release
ARTIFACT := target/$(TARGET)/$(PROFILE)/bootstrap
PACKAGE_DIR := dist
PACKAGE := $(PACKAGE_DIR)/backcountry-rust-runtime.zip

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
	cargo build --locked --release --target $(TARGET)

package: build
	install -d $(PACKAGE_DIR)
	install -m 0755 $(ARTIFACT) $(PACKAGE_DIR)/bootstrap
	cd $(PACKAGE_DIR) && zip -q -X backcountry-rust-runtime.zip bootstrap

clean:
	cargo clean
	rm -rf $(PACKAGE_DIR)
