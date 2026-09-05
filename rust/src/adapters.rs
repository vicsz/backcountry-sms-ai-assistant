//! Explicit side-effect seams. Implementations are injected into the deterministic core.

use crate::models::{
    ContextInteraction, Coordinates, FireBanResult, LocationResolution, RetrievalResult,
    WeatherPeriod,
};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdapterError {
    pub category: String,
}
impl AdapterError {
    pub fn new(category: &str) -> Self {
        Self {
            category: category.to_owned(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModelOperation {
    Interpret,
    General,
    Clarify,
    LocationRequest,
    CoordinateCorrection,
    WeatherUnavailable,
    Advice,
    RagResponse,
}
impl ModelOperation {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Interpret => "interpretation",
            Self::General => "general",
            Self::Clarify => "clarification",
            Self::LocationRequest => "location_request",
            Self::CoordinateCorrection => "coordinate_correction",
            Self::WeatherUnavailable => "weather_unavailable",
            Self::Advice => "weather_advice",
            Self::RagResponse => "rag_response",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ModelRequest {
    pub operation: ModelOperation,
    pub user_text: String,
    pub history: Vec<ContextInteraction>,
    pub evidence: Option<String>,
    pub max_tokens: u16,
    pub temperature: f32,
}
#[derive(Debug, Clone)]
pub struct ContextLoad {
    pub history: Vec<ContextInteraction>,
    pub readable: bool,
}
#[derive(Debug, Clone)]
pub struct TelemetryEvent {
    pub event: String,
    pub status: String,
    pub provider: Option<String>,
    pub intent: Option<String>,
    pub outcome: Option<String>,
    pub metrics: BTreeMap<String, f64>,
}

pub trait ModelClient {
    fn converse(&mut self, request: ModelRequest) -> Result<String, AdapterError>;
}
pub trait LocationResolver {
    fn resolve(&mut self, query: &str) -> Result<LocationResolution, AdapterError>;
}
pub trait WeatherProvider {
    fn forecast(&mut self, coordinates: Coordinates) -> Result<Vec<WeatherPeriod>, AdapterError>;
}
pub trait ContextStore {
    fn load(&mut self, sender: &str) -> Result<ContextLoad, AdapterError>;
    fn reserve(
        &mut self,
        sender: &str,
        message_id: &str,
        created_at: &str,
        input: &str,
    ) -> Result<bool, AdapterError>;
    fn complete(
        &mut self,
        sender: &str,
        message_id: &str,
        created_at: &str,
        input: &str,
        output: &str,
    ) -> Result<(), AdapterError>;
}
pub trait Retriever {
    fn retrieve(&mut self, question: &str) -> Result<Vec<RetrievalResult>, AdapterError>;
}
pub trait FireBanProvider {
    fn lookup(&mut self, coordinates: Coordinates) -> Result<FireBanResult, AdapterError>;
}
pub trait SmsSender {
    fn send(&mut self, destination: &str, body: &str) -> Result<(), AdapterError>;
}
pub trait TelemetrySink {
    fn emit(&mut self, event: TelemetryEvent);
    fn snapshot(&self) -> BTreeMap<String, usize> {
        BTreeMap::new()
    }
}

pub struct Services {
    pub model: Box<dyn ModelClient>,
    pub location: Box<dyn LocationResolver>,
    pub weather: Box<dyn WeatherProvider>,
    pub context: Box<dyn ContextStore>,
    pub retriever: Box<dyn Retriever>,
    pub fire_ban: Box<dyn FireBanProvider>,
    pub sms: Box<dyn SmsSender>,
    pub telemetry: Box<dyn TelemetrySink>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RetryPolicy {
    pub connect_timeout_seconds: u64,
    pub read_timeout_seconds: u64,
    pub max_attempts: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdapterSeam {
    pub name: &'static str,
    pub policy: RetryPolicy,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductionAdapterConfig {
    pub model_id: String,
    pub knowledge_base_id: String,
    pub context_table: String,
    pub weather_url: String,
    pub geocoding_url: String,
    pub bedrock_converse: AdapterSeam,
    pub bedrock_retrieve: AdapterSeam,
    pub dynamodb: AdapterSeam,
    pub location: AdapterSeam,
    pub weather: AdapterSeam,
    pub athena: AdapterSeam,
    pub sms: AdapterSeam,
}

impl ProductionAdapterConfig {
    /// Capture the current Python adapter budgets without reading credentials or payload data.
    pub fn from_env() -> Result<Self, AdapterError> {
        let model_id = std::env::var("BEDROCK_MODEL_ID")
            .unwrap_or_else(|_| crate::models::DEFAULT_MODEL_ID.into());
        if !matches!(
            model_id.as_str(),
            crate::models::DEFAULT_MODEL_ID | crate::models::NOVA_MICRO_MODEL_ID
        ) {
            return Err(AdapterError::new("invalid_model_id"));
        }
        Ok(Self {
            model_id,
            knowledge_base_id: std::env::var("RAG_KNOWLEDGE_BASE_ID").unwrap_or_default(),
            context_table: std::env::var("MESSAGE_CONTEXT_TABLE").unwrap_or_default(),
            weather_url: "https://api.open-meteo.com/v1/forecast".into(),
            geocoding_url: "https://geogratis.gc.ca/services/geoname/en/geonames".into(),
            bedrock_converse: AdapterSeam {
                name: "bedrock_converse",
                policy: RetryPolicy {
                    connect_timeout_seconds: 8,
                    read_timeout_seconds: 8,
                    max_attempts: 3,
                },
            },
            bedrock_retrieve: AdapterSeam {
                name: "bedrock_retrieve",
                policy: RetryPolicy {
                    connect_timeout_seconds: 1,
                    read_timeout_seconds: 4,
                    max_attempts: 1,
                },
            },
            dynamodb: AdapterSeam {
                name: "dynamodb",
                policy: RetryPolicy {
                    connect_timeout_seconds: 2,
                    read_timeout_seconds: 2,
                    max_attempts: 3,
                },
            },
            location: AdapterSeam {
                name: "location",
                policy: RetryPolicy {
                    connect_timeout_seconds: 3,
                    read_timeout_seconds: 3,
                    max_attempts: 1,
                },
            },
            weather: AdapterSeam {
                name: "weather",
                policy: RetryPolicy {
                    connect_timeout_seconds: 3,
                    read_timeout_seconds: 3,
                    max_attempts: 3,
                },
            },
            athena: AdapterSeam {
                name: "athena",
                policy: RetryPolicy {
                    connect_timeout_seconds: 2,
                    read_timeout_seconds: 5,
                    max_attempts: 1,
                },
            },
            sms: AdapterSeam {
                name: "sms",
                policy: RetryPolicy {
                    connect_timeout_seconds: 5,
                    read_timeout_seconds: 5,
                    max_attempts: 1,
                },
            },
        })
    }
}
