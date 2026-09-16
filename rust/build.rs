fn main() {
    println!("cargo:rerun-if-env-changed=BUILD_COMMIT");
    println!("cargo:rerun-if-env-changed=BUILD_TIME_UTC");
}
