use crate::event::InboundMessage;
use std::{env, error::Error, fmt};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeliveryConfig {
    pub test_mode: bool,
    pub deployment_environment: String,
    pub delivery_mode: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DeliveryConfigError {
    InvalidTestMode,
    InvalidDeliveryMode,
    CaptureModeNotPermitted,
    TestModeRequiresCapture,
}

impl fmt::Display for DeliveryConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let reason = match self {
            Self::InvalidTestMode => "invalid_test_mode",
            Self::InvalidDeliveryMode => "invalid_sms_delivery_mode",
            Self::CaptureModeNotPermitted => "capture_mode_not_permitted",
            Self::TestModeRequiresCapture => "test_mode_requires_capture",
        };
        formatter.write_str(reason)
    }
}

impl Error for DeliveryConfigError {}

impl DeliveryConfig {
    pub fn from_env() -> Result<Self, DeliveryConfigError> {
        let test_mode_value = env::var("TEST_MODE").unwrap_or_else(|_| "false".to_owned());
        let delivery_mode = env::var("SMS_DELIVERY_MODE").unwrap_or_else(|_| "live".to_owned());
        let deployment_environment = env::var("DEPLOYMENT_ENVIRONMENT")
            .unwrap_or_else(|_| "production".to_owned())
            .trim()
            .to_owned();
        Self::from_values(&test_mode_value, &delivery_mode, &deployment_environment)
    }

    pub fn from_values(
        test_mode_value: &str,
        delivery_mode_value: &str,
        deployment_environment_value: &str,
    ) -> Result<Self, DeliveryConfigError> {
        let test_mode = match test_mode_value.trim().to_ascii_lowercase().as_str() {
            "true" => true,
            "false" => false,
            _ => return Err(DeliveryConfigError::InvalidTestMode),
        };
        let delivery_mode = delivery_mode_value.trim().to_ascii_lowercase();
        let deployment_environment = deployment_environment_value.trim().to_ascii_lowercase();
        if !matches!(delivery_mode.as_str(), "capture" | "live")
            || !matches!(deployment_environment.as_str(), "production" | "test")
        {
            return Err(DeliveryConfigError::InvalidDeliveryMode);
        }
        if delivery_mode == "capture" && (!test_mode || deployment_environment != "test") {
            return Err(DeliveryConfigError::CaptureModeNotPermitted);
        }
        if test_mode && delivery_mode != "capture" {
            return Err(DeliveryConfigError::TestModeRequiresCapture);
        }
        Ok(Self {
            test_mode,
            deployment_environment,
            delivery_mode,
        })
    }

    pub fn is_capture(&self) -> bool {
        self.delivery_mode == "capture"
    }
}

pub fn normalized_e164(value: &str) -> String {
    let digits: String = value.chars().filter(char::is_ascii_digit).collect();
    if (8..=15).contains(&digits.len()) {
        format!("+{digits}")
    } else {
        String::new()
    }
}

pub fn sender_allowed(message: &InboundMessage, allowed: Option<&str>) -> bool {
    let Some(allowed) = allowed else { return false };
    message.origination_number == allowed
        || (!normalized_e164(&message.origination_number).is_empty()
            && normalized_e164(&message.origination_number) == normalized_e164(allowed))
}
