use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::{fmt, sync::OnceLock};

pub const DEFAULT_MODEL_ID: &str = "us.amazon.nova-2-lite-v1:0";
pub const NOVA_MICRO_MODEL_ID: &str = "us.amazon.nova-micro-v1:0";
pub const CONTEXT_HISTORY_LIMIT: usize = 5;
pub const CONTEXT_TTL_SECONDS: i64 = 7 * 24 * 60 * 60;
pub const MAX_SMS_SEPTETS: usize = 160;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Coordinates {
    pub latitude: f64,
    pub longitude: f64,
}

impl Coordinates {
    pub fn is_valid(self) -> bool {
        self.latitude.is_finite()
            && self.longitude.is_finite()
            && (-90.0..=90.0).contains(&self.latitude)
            && (-180.0..=180.0).contains(&self.longitude)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ContextInteraction {
    pub input_body: String,
    pub output_body: String,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LocationCandidate {
    pub name: String,
    pub coordinates: Coordinates,
    pub feature_type: String,
    pub region: String,
    pub source: String,
    pub score: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LocationResolution {
    pub candidate: Option<LocationCandidate>,
    pub outcome: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeatherPeriod {
    pub time: String,
    pub temperature_c: f64,
    pub precipitation_probability: f64,
    pub precipitation_mm: f64,
    pub rain_mm: f64,
    pub wind_kmh: f64,
    pub gust_kmh: f64,
    pub weather_code: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RetrievalCitation {
    pub park_name: String,
    pub section: String,
    pub source_url: String,
    pub source_label: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RetrievalResult {
    pub excerpt: String,
    pub citation: RetrievalCitation,
    pub score_millis: u32,
    pub claims: Vec<(String, String)>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FireBanResult {
    pub park_name: Option<String>,
    pub jurisdiction: String,
    pub status: String,
    pub source_as_of: Option<String>,
    pub retrieved_at: Option<String>,
    pub source_url: Option<String>,
    pub source_hash: Option<String>,
    pub snapshot_id: Option<String>,
    pub freshness: String,
    pub boundary: String,
    pub uncertainty: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FireBanPark {
    pub park_id: String,
    pub park_name: String,
    pub geometry_wkt: String,
    pub source_name: String,
    pub source_url: String,
    pub source_record_id: String,
    pub source_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FireBanStatus {
    pub source_name: String,
    pub source_url: String,
    pub source_record_id: String,
    pub source_hash: String,
    pub jurisdiction: String,
    pub park_id: String,
    pub park_name: String,
    pub alert_type: String,
    pub normalized_status: String,
    pub raw_wording: String,
    pub source_as_of: String,
    pub retrieved_at: String,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FireBanSnapshot {
    pub schema_version: String,
    pub snapshot_id: String,
    pub snapshot_created_at: String,
    pub parks: Vec<FireBanPark>,
    pub statuses: Vec<FireBanStatus>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Interpretation {
    pub intent: String,
    pub location_text: Option<String>,
    pub current_location_text: String,
    pub coordinates: Option<Coordinates>,
    pub time_window: String,
    pub activity: String,
    pub location_source: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ModelOutputError {
    TooLarge,
    InvalidJson,
    NotObject,
    UnexpectedKeys,
    InvalidField(&'static str),
}

impl fmt::Display for ModelOutputError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::TooLarge => formatter.write_str("model_output_too_large"),
            Self::InvalidJson => formatter.write_str("invalid_model_json"),
            Self::NotObject => formatter.write_str("model_output_not_object"),
            Self::UnexpectedKeys => formatter.write_str("unexpected_model_schema_keys"),
            Self::InvalidField(field) => write!(formatter, "invalid_model_field:{field}"),
        }
    }
}

impl std::error::Error for ModelOutputError {}

/// Parse the exact Stage 4.1 interpretation shape without permitting model-added fields.
///
/// The Python oracle accepts a JSON object embedded in a fenced or explanatory response, so
/// this parser does the same bounded scan while retaining strict validation of the object.
pub fn parse_interpretation(output: &str) -> Result<Interpretation, ModelOutputError> {
    if output.len() > 4096 {
        return Err(ModelOutputError::TooLarge);
    }
    let value = serde_json::from_str::<Value>(output)
        .ok()
        .or_else(|| {
            output
                .char_indices()
                .filter(|(_, character)| *character == '{')
                .find_map(|(index, _)| {
                    let mut deserializer = serde_json::Deserializer::from_str(&output[index..]);
                    Value::deserialize(&mut deserializer).ok()
                })
        })
        .ok_or(ModelOutputError::InvalidJson)?;
    let object = value.as_object().ok_or(ModelOutputError::NotObject)?;
    parse_interpretation_object(object)
}

/// Apply the deterministic grounding rules that follow model interpretation in the Python oracle.
/// The model may extract a candidate, but it is never allowed to authorize a location or
/// coordinate that is not grounded in the current SMS or readable sender history.
pub fn normalize_interpretation(
    mut interpretation: Interpretation,
    current_sms: &str,
    history: &[ContextInteraction],
) -> Option<Interpretation> {
    if interpretation.location_source == "history"
        && crate::domain::parse_coordinates(current_sms).is_none()
    {
        interpretation.coordinates = None;
    }
    if crate::domain::parse_coordinates(current_sms).is_some() {
        interpretation.location_source = "current".into();
    }

    let mut location = short_ascii(interpretation.location_text.as_deref().unwrap_or_default());
    let mut current_location = short_ascii(&interpretation.current_location_text);
    let history_location = newest_history_location(history);

    if interpretation.location_source == "current"
        && !current_location.is_empty()
        && !contains_case_insensitive(current_sms, &current_location)
    {
        let candidate_location = canonical_history_location(&location, history);
        let candidate_current = canonical_history_location(&current_location, history);
        if !history_location.is_empty()
            && (history_location_is_grounded(&candidate_location, history)
                || history_location_is_grounded(&candidate_current, history))
        {
            interpretation.location_source = "history".into();
            location = if history_location_is_grounded(&candidate_location, history) {
                candidate_location
            } else {
                candidate_current
            };
            current_location.clear();
        }
    }
    if interpretation.location_source == "current"
        && !location.is_empty()
        && !current_location.is_empty()
        && !contains_case_insensitive(current_sms, &current_location)
        && history_location_is_grounded(&location, history)
    {
        interpretation.location_source = "history".into();
        current_location.clear();
    }
    if interpretation.location_source == "current"
        && interpretation.coordinates.is_none()
        && !current_location.is_empty()
        && !contains_case_insensitive(current_sms, &current_location)
    {
        return None;
    }
    if interpretation.location_source == "history" {
        location = canonical_history_location(&location, history);
        if is_deictic_location(&location) {
            location = history_location.clone();
        }
    }
    if interpretation.intent != "information_lookup"
        && interpretation.location_source == "current"
        && !location.is_empty()
        && current_location.is_empty()
        && contains_case_insensitive(current_sms, &location)
    {
        current_location = location.clone();
    }

    if interpretation.intent != "information_lookup"
        && !location.is_empty()
        && interpretation.coordinates.is_none()
    {
        match interpretation.location_source.as_str() {
            "none" => return None,
            "current" if current_location.is_empty() || location != current_location => {
                return None
            }
            "history" if !history_location_is_grounded(&location, history) => return None,
            _ => {}
        }
    }
    if interpretation.intent != "information_lookup"
        && !current_location.is_empty()
        && (interpretation.location_source != "current" || location != current_location)
    {
        return None;
    }

    interpretation.location_text = if location.is_empty() {
        None
    } else {
        Some(location)
    };
    interpretation.current_location_text = current_location;
    interpretation.time_window = if contains_case_insensitive(current_sms, "now")
        || contains_case_insensitive(current_sms, "right now")
        || contains_case_insensitive(current_sms, "currently")
    {
        "now".into()
    } else {
        short_ascii(&interpretation.time_window)
    };
    interpretation.activity = short_ascii(&interpretation.activity);
    if interpretation.time_window.is_empty() {
        interpretation.time_window = "today".into();
    }
    if interpretation.activity.is_empty() {
        interpretation.activity = "general".into();
    }
    Some(interpretation)
}

fn short_ascii(value: &str) -> String {
    crate::gsm7::bound_sms(&value.chars().take(48).collect::<String>(), "")
}

fn contains_case_insensitive(text: &str, needle: &str) -> bool {
    !needle.is_empty()
        && text
            .to_ascii_lowercase()
            .contains(&needle.to_ascii_lowercase())
}

fn history_locations(text: &str) -> Vec<String> {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    let pattern =
        PATTERN.get_or_init(|| Regex::new(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b").unwrap());
    pattern
        .find_iter(text)
        .map(|value| value.as_str().to_owned())
        .filter(|value| {
            !matches!(
                value.to_ascii_lowercase().as_str(),
                "weather"
                    | "forecast"
                    | "today"
                    | "tomorrow"
                    | "tonight"
                    | "please"
                    | "can"
                    | "could"
                    | "what"
                    | "when"
            )
        })
        .collect()
}

fn newest_history_location(history: &[ContextInteraction]) -> String {
    history
        .iter()
        .rev()
        .flat_map(|item| {
            history_locations(&item.input_body)
                .into_iter()
                .chain(history_locations(&item.output_body))
        })
        .max_by_key(String::len)
        .unwrap_or_default()
}

fn history_location_is_grounded(location: &str, history: &[ContextInteraction]) -> bool {
    !location.is_empty()
        && history.iter().rev().any(|item| {
            contains_case_insensitive(&item.input_body, location)
                || history_locations(&item.input_body)
                    .into_iter()
                    .chain(history_locations(&item.output_body))
                    .any(|label| label.eq_ignore_ascii_case(location))
        })
}

fn canonical_history_location(location: &str, history: &[ContextInteraction]) -> String {
    history_locations_from_context(history)
        .into_iter()
        .filter(|candidate| contains_case_insensitive(location, candidate))
        .max_by_key(String::len)
        .unwrap_or_else(|| location.to_owned())
}

fn history_locations_from_context(history: &[ContextInteraction]) -> Vec<String> {
    history
        .iter()
        .flat_map(|item| {
            history_locations(&item.input_body)
                .into_iter()
                .chain(history_locations(&item.output_body))
        })
        .collect()
}

fn is_deictic_location(value: &str) -> bool {
    matches!(
        value.to_ascii_lowercase().as_str(),
        "here"
            | "there"
            | "this lake"
            | "that lake"
            | "the lake"
            | "this park"
            | "that park"
            | "the park"
            | "this place"
            | "that place"
            | "the place"
    )
}

fn parse_interpretation_object(
    object: &Map<String, Value>,
) -> Result<Interpretation, ModelOutputError> {
    const KEYS: [&str; 7] = [
        "intent",
        "location_text",
        "current_location_text",
        "coordinates",
        "time_window",
        "activity",
        "location_source",
    ];
    if object.len() != KEYS.len() || KEYS.iter().any(|key| !object.contains_key(*key)) {
        return Err(ModelOutputError::UnexpectedKeys);
    }
    let intent = string_field(object, "intent")?;
    if !matches!(
        intent.as_str(),
        "weather" | "fire_status" | "information_lookup" | "general" | "unclear"
    ) {
        return Err(ModelOutputError::InvalidField("intent"));
    }
    let location_text = match object.get("location_text") {
        Some(Value::Null) => None,
        Some(Value::String(value)) => Some(value.clone()),
        _ => return Err(ModelOutputError::InvalidField("location_text")),
    };
    let current_location_text = string_field(object, "current_location_text")?;
    let coordinates = match object.get("coordinates") {
        Some(Value::Null) => None,
        Some(Value::Object(value)) => {
            if value.len() != 2
                || !value.contains_key("latitude")
                || !value.contains_key("longitude")
            {
                return Err(ModelOutputError::InvalidField("coordinates"));
            }
            let latitude = number_field(value, "latitude")?;
            let longitude = number_field(value, "longitude")?;
            let coordinates = Coordinates {
                latitude,
                longitude,
            };
            if !coordinates.is_valid() {
                return Err(ModelOutputError::InvalidField("coordinates"));
            }
            Some(coordinates)
        }
        _ => return Err(ModelOutputError::InvalidField("coordinates")),
    };
    let time_window_value = optional_string_field(object, "time_window")?;
    let activity_value = optional_string_field(object, "activity")?;
    let location_source = string_field(object, "location_source")?;
    if !matches!(location_source.as_str(), "current" | "history" | "none") {
        return Err(ModelOutputError::InvalidField("location_source"));
    }
    // The Python oracle tolerates null qualifiers for information lookups and applies the same
    // bounded defaults used for weather. Other intents retain strict schema validation.
    let (time_window, activity) = if intent == "information_lookup" {
        (
            time_window_value.unwrap_or_else(|| "today".to_owned()),
            activity_value.unwrap_or_else(|| "general".to_owned()),
        )
    } else {
        (
            time_window_value.ok_or(ModelOutputError::InvalidField("time_window"))?,
            activity_value.ok_or(ModelOutputError::InvalidField("activity"))?,
        )
    };
    Ok(Interpretation {
        intent,
        location_text,
        current_location_text,
        coordinates,
        time_window,
        activity,
        location_source,
    })
}

fn optional_string_field(
    object: &Map<String, Value>,
    field: &'static str,
) -> Result<Option<String>, ModelOutputError> {
    match object.get(field) {
        Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value.clone())),
        _ => Err(ModelOutputError::InvalidField(field)),
    }
}

fn string_field(
    object: &Map<String, Value>,
    field: &'static str,
) -> Result<String, ModelOutputError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .ok_or(ModelOutputError::InvalidField(field))
}

fn number_field(object: &Map<String, Value>, field: &'static str) -> Result<f64, ModelOutputError> {
    object
        .get(field)
        .and_then(Value::as_f64)
        .filter(|number| number.is_finite())
        .ok_or(ModelOutputError::InvalidField(field))
}
