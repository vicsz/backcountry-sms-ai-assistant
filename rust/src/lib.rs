//! Safe, compileable first slice of the Stage 11 Rust runtime migration.
//!
//! The deterministic orchestration remains separate from the concrete AWS/HTTP adapters. The
//! active deployed request path remains Python until the parity and cutover gates in the Stage 11
//! specification pass.

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
