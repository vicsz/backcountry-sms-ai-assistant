//! Rust request runtime for the Stage 11 application-runtime migration.
//!
//! Deterministic orchestration remains separate from the concrete AWS/HTTP adapters. The Python
//! modules remain support/evaluation code; the deployed Demo request path is Rust.

pub mod adapters;
pub mod domain;
pub mod event;
pub mod fakes;
pub mod gsm7;
pub mod models;
pub mod policy;
pub mod production;
pub mod runtime;

pub use event::{parse_sns_event, InboundMessage};
pub use models::{parse_interpretation, Coordinates, Interpretation, ModelOutputError};
pub use policy::{normalized_e164, DeliveryConfig, DeliveryConfigError};
pub use runtime::{handle_event, RuntimeResponse};
