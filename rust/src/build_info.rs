//! Build identity exposed by the deterministic `build`/`status` command.

const UNKNOWN: &str = "unknown";

pub const BUILD_COMMIT: &str = match option_env!("BUILD_COMMIT") {
    Some(value) => value,
    None => UNKNOWN,
};
pub const BUILD_TIME_UTC: &str = match option_env!("BUILD_TIME_UTC") {
    Some(value) => value,
    None => UNKNOWN,
};

pub fn is_command(text: &str) -> bool {
    let command = text
        .trim()
        .trim_end_matches(['?', '!', '.'])
        .to_ascii_lowercase();
    matches!(
        command.as_str(),
        "build" | "status" | "build status" | "status build"
    )
}

pub fn reply_for_metadata(commit: &str, build_time_utc: &str) -> String {
    if commit == UNKNOWN || build_time_utc == UNKNOWN {
        return "Build metadata unavailable.".into();
    }
    format!("Build {commit} {build_time_utc}")
}

pub fn reply(text: &str) -> Option<String> {
    is_command(text).then(|| reply_for_metadata(BUILD_COMMIT, BUILD_TIME_UTC))
}
