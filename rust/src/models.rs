use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fmt;

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
