use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InboundMessage {
    pub origination_number: String,
    pub message_body: String,
    pub message_id: String,
    pub timestamp: String,
}

#[derive(Debug, Deserialize)]
struct SnsEvent {
    #[serde(rename = "Records")]
    records: Vec<SnsRecord>,
}

#[derive(Debug, Deserialize)]
struct SnsRecord {
    #[serde(rename = "Sns")]
    sns: Option<SnsEnvelope>,
}

#[derive(Debug, Deserialize)]
struct SnsEnvelope {
    #[serde(rename = "Message")]
    message: Option<String>,
    #[serde(rename = "MessageId", default)]
    message_id: String,
    #[serde(rename = "Timestamp", default)]
    timestamp: String,
}

#[derive(Debug, Deserialize)]
struct ProviderMessage {
    #[serde(rename = "originationNumber")]
    origination_number: Option<String>,
    #[serde(rename = "messageBody")]
    message_body: Option<String>,
}

/// Parse only the first SNS record, matching the existing Python handler's bounded contract.
pub fn parse_sns_event(event: &Value) -> Option<InboundMessage> {
    let envelope: SnsEvent = serde_json::from_value(event.clone()).ok()?;
    let sns = envelope.records.first()?.sns.as_ref()?;
    let message: ProviderMessage = serde_json::from_str(sns.message.as_deref()?).ok()?;
    Some(InboundMessage {
        origination_number: message.origination_number?,
        message_body: message.message_body?,
        message_id: sns.message_id.clone(),
        timestamp: sns.timestamp.clone(),
    })
}
